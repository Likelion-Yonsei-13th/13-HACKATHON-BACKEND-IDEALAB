import os
import requests
from typing import Dict, Any, Iterator, List
import logging
from urllib.parse import urlencode
logger = logging.getLogger(__name__)


SEOUL_API_KEY = os.getenv("SEOUL_OPENAPI_KEY", "").strip()

BASE = "http://openapi.seoul.go.kr:8088"

def fetch_TbgisTrdarRelm(start: int, end: int) -> Dict[str, Any]:
    if not SEOUL_API_KEY:
        raise RuntimeError("SEOUL_API_KEY not set")
    url = f"{BASE}/{SEOUL_API_KEY}/json/TbgisTrdarRelm/{start}/{end}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()

def iter_TbgisTrdarRelm(page_size: int = 1000) -> Iterator[Dict[str, Any]]:
    """
    페이지네이션 반복자 (list_total_count를 이용해 전량 조회)
    """
    start, end = 1, page_size
    first = fetch_TbgisTrdarRelm(start, end)
    root = first.get("TbgisTrdarRelm", {})
    total = int(root.get("list_total_count", 0))
    rows = root.get("row", []) or []
    for r in rows:
        yield r
    while end < total:
        start = end + 1
        end = min(end + page_size, total)
        js = fetch_TbgisTrdarRelm(start, end)
        rows = js.get("TbgisTrdarRelm", {}).get("row", []) or []
        for r in rows:
            yield r

def iter_industry_metrics(trdar: str, year: str | None = None, page_size: int = 1000):
    """
    서울 상권분석 '업종/매출' 계열을 상권(trdar) 단위로 순회하는 제너레이터.
    - 응답 스키마가 API 버전에 따라 조금씩 달라 널가드 + 키 다중 대응.
    - year(yyq) 필터가 오면 가급적 반영.
    """
    # 내부에 이미 구현되어 있는 요청/페이지네이션 유틸을 그대로 사용하세요.
    # 여기서는 레코드(r) 파싱만 강건하게 바꿉니다.

    def _pick(d, *keys):
        for k in keys:
            v = d.get(k)
            if v not in (None, "", "NULL", "NaN"):
                return v
        return None

    # 예시: 기존 코드처럼 페이지네이션 루프가 있다 가정
    for r in fetch_service_rows("INDUSTRY_METRICS", trdar=trdar, year=year, page_size=page_size):
        # 연/분기
        yy  = _pick(r, "STDR_YY", "STDR_YR", "BASE_YEAR")
        qu  = _pick(r, "STDR_QU", "QU", "QUARTER")
        yyq = _pick(r, "STDR_YYQU_CD") or (f"{yy}Q{qu}" if yy and qu else None)

        # 숫자 필드(있으면 사용)
        thsmon_amt = _pick(r, "THSMON_SELNG_AMT", "THSMON_SELLNG_AMT")
        thsmon_co  = _pick(r, "THSMON_SELNG_CO",  "THSMON_SELLNG_CO")
        mdwk_amt   = _pick(r, "MDWK_SELNG_AMT",   "MDWK_SELLNG_AMT")
        wkend_amt  = _pick(r, "WKEND_SELNG_AMT",  "WKEND_SELLNG_AMT")

        yield {
            "trdar_cd": _pick(r, "TRDAR_CD"),
            "yyq": yyq,
            "svc_induty_cd": _pick(r, "SVC_INDUTY_CD"),
            "svc_induty_cd_nm": _pick(r, "SVC_INDUTY_CD_NM"),
            "thsmon_selng_amt": thsmon_amt,
            "thsmon_selng_co":  thsmon_co,
            "mdwk_selng_amt":   mdwk_amt,
            "wkend_selng_amt":  wkend_amt,
        }
        
def _build_url(service: str, start: int, end: int, params: dict) -> str:
    """
    경로형식(권장): /{KEY}/json/{SERVICE}/{START}/{END}?q=...
    """
    if not SEOUL_API_KEY:
        raise RuntimeError("SEOUL_OPENAPI_KEY is not set")

    # TYPE=json을 경로에 명시(확실) + 쿼리에는 중복 방지
    base = f"http://openapi.seoul.go.kr:8088/{SEOUL_API_KEY}/json/{service}/{start}/{end}"
    params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    qs = urlencode(params, doseq=True)
    return f"{base}?{qs}" if qs else base

def fetch_service(service: str, start: int, end: int, **params):
    url = _build_url(service, start, end, params)
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    text = resp.text.strip()

    # 혹시나 HTML/XML이 오면 바로 에러 메시지 노출
    if not text.startswith("{"):
        raise ValueError(f"Non-JSON response (did you set correct service/params?): url={url} body_starts={text[:120]!r}")

    payload = resp.json()
    block = payload.get(service) or next((v for k, v in payload.items() if isinstance(v, dict) and k.lower().startswith(service.lower()[:5])), {})
    header = (block or {}).get("RESULT") or (payload.get("RESULT") if isinstance(payload.get("RESULT"), dict) else {})
    rows = (block or {}).get("row") or []

    return payload, rows, header, url
