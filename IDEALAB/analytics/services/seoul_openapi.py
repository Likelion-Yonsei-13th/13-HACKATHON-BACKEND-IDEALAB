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

def iter_industry_metrics(trdar=None, year=None):
    """
    서울열린데이터 '유망업종/평균매출/성장률/상권변화지표' API 호출 → dict 반복자
    (API 실제 스펙에 맞춰 SERVICE 이름, 필드명 수정 필요)
    """
    base_url = "http://openapi.seoul.go.kr:8088"
    service = "VwsmTrdarSelngQq"  # 실제 서비스명으로 교체 필요
    start, end = 1, 1000

    while True:
        url = f"{base_url}/{SEOUL_API_KEY}/json/{service}/{start}/{end}"
        params = {}
        if trdar:
            params["TRDAR_CD"] = trdar
        if year:
            params["STDR_YY"] = year

        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json().get(service, {})
        rows = data.get("row", [])
        if not rows:
            break

        for r in rows:
            yield {
                "trdar_cd": r.get("TRDAR_CD"),
                "year": int(r.get("STDR_YY")),
                "avg_sales": float(r.get("AVG_SALE", 0)),
                "growth_rate": float(r.get("GROWTH_RATE", 0)),
                "closure_rate": float(r.get("CLOSURE_RATE", 0)),
                "change_index": float(r.get("CHANGE_IDX", 0)),
            }

        start += 1000
        end += 1000

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
