# keywords/services/rules.py
import os, re, json, urllib.parse
from typing import Dict, Any, List, Optional, Set
from django.utils import timezone
from openai import OpenAI
from meetings.models import Meeting
from keywords.models import KeywordLog

# ── (1) 엔드포인트 표준 (slug → URL 경로)
API_BASE = "/api/analytics"
METRICS_TO_ENDPOINT: Dict[str, str] = {
    # 문서 #1
    "analytics/store-counts":   f"{API_BASE}/store-counts/",
    # 문서 #2
    "market/change-index":      f"{API_BASE}/change-index/",
    # 문서 #3
    "stores/closures":          f"{API_BASE}/closures/",
    # 문서 #4
    "industry/metrics":         f"{API_BASE}/industry-metrics/",
    # 문서 #5
    "sales/estimates":          f"{API_BASE}/sales-estimates/",
    # (옵션) 내부용 – 좌표 필요 시 rules가 참고만 함
    "region/center":            f"{API_BASE}/region/center/",
}

# ── (2) 감지 가능한 메트릭(화이트리스트) → 반드시 위 슬러그 중 하나여야 함
METRIC_CATALOG = [
    # 문서 #1
    {"canonical": "업종별 점포수", "slug": "analytics/store-counts",
     "synonyms": ["업종 포화도","포화도","점포 수","상점 수","경쟁도"]},

    # 문서 #2
    {"canonical": "상권변화지표", "slug": "market/change-index",
     "synonyms": ["상권 변화","상권 변화 지수","변화지수","변화지표"]},

    # 문서 #3
    {"canonical": "폐업 통계", "slug": "stores/closures",
     "synonyms": ["폐업률","폐업 수","폐점률","폐점 통계"]},

    # 문서 #4
    {"canonical": "산업 지표", "slug": "industry/metrics",
     "synonyms": ["산업지표","업종 지표","매출 지표","업종 매출 비중"]},

    # 문서 #5
    {"canonical": "추정매출", "slug": "sales/estimates",
     "synonyms": ["상권 추정 매출","추정 매출","예상 매출"]},

    # (옵션) 내부 보조 – 좌표/지도 필요할 때만
    {"canonical": "상권 중심좌표", "slug": "region/center",
     "synonyms": ["상권 좌표","좌표","중심좌표"]},
]
_ALLOWED_CANONICAL: Set[str] = {m["canonical"] for m in METRIC_CATALOG}
_CANONICAL_TO_SLUG: Dict[str, str] = {m["canonical"]: m["slug"] for m in METRIC_CATALOG}
_SYNONYM_TO_CANONICAL: Dict[str, str] = {s: m["canonical"] for m in METRIC_CATALOG for s in m["synonyms"]}

# ── (3) 지역 표준화(초기 seed) — 필요한 만큼 추가
ALIAS_LOCATION_TO_SLUG = {
    "홍대":"hongdae","홍대입구":"hongdae","홍익대":"hongdae","서교동":"hongdae",
    "강남":"gangnam","강남역":"gangnam",
    "신촌":"sinchon","연세대":"sinchon","연대":"sinchon",
    "건대":"geondae","건대입구":"geondae",
    "잠실":"jamsil",
}
SLUG_TO_TRDAR = {  # ★ 실제 TRDAR_CD로 보강
    "hongdae":"3110008","gangnam":"3130001","sinchon":"3110003","geondae":"3110005","jamsil":"3220008",
}

# ── (4) LLM은 엔티티만. 메트릭은 화이트리스트로 감지.
_client = None
def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

LLM_SYSTEM = (
    "You are a keyword detector for a Korean startup workspace. "
    'Return strict JSON: {"entities":[],"metrics":[],"intents":[]}'
)

def _contains_token(text: str, token: str) -> bool:
    pat = rf'(?<![가-힣0-9A-Za-z]){re.escape(token)}(?![가-힣0-9A-Za-z])'
    return re.search(pat, text) is not None

def _detect_metrics(text: str) -> List[str]:
    found = set()
    for c in _ALLOWED_CANONICAL:
        if _contains_token(text, c): found.add(c)
    for syn, c in _SYNONYM_TO_CANONICAL.items():
        if _contains_token(text, syn): found.add(c)
    return sorted(_CANONICAL_TO_SLUG[c] for c in sorted(found))

def _detect_entities(text: str) -> List[str]:
    ents: List[str] = []
    try:
        resp = get_client().chat.completions.create(
            model=os.getenv("OPENAI_KEYWORDS_MODEL","gpt-4o-mini"),
            messages=[{"role":"system","content":LLM_SYSTEM},{"role":"user","content":text}],
            temperature=0.2, response_format={"type":"json_object"},
        )
        raw = resp.choices[0].message.content
        parsed = json.loads(raw)
        ents = [e for e in parsed.get("entities",[]) if isinstance(e,str)]
    except Exception:
        ents = []
    # 사전 기반 보강(지역 키워드)
    for k in ALIAS_LOCATION_TO_SLUG.keys():
        if _contains_token(text, k): ents.append(k)
    return sorted(set(ents))

def _qs(params: Dict[str, Any]) -> str:
    p = {k: v for k, v in params.items() if v not in (None, "", [], {})}
    return "?" + urllib.parse.urlencode(p, doseq=True) if p else ""

def build_api_links(
    text: str,
    *,
    # 공통 기본값
    radius: int = 2000, group_by: str = "mcls", limit: int = 10,
    # 문서별 선택 파라미터를 외부에서 넣을 수도 있게 허용
    yyq: Optional[str] = None, year: Optional[int] = None,
    signgu_cd: Optional[str] = None, adstrd_cd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    문장을 받아 '바로 호출 가능한' API 링크 배열을 생성.
    - 지역 키워드 → trdar_cd
    - 감지된 메트릭 → 고정 엔드포인트 매핑
    - 각 엔드포인트 스펙에 맞춰 쿼리 구성
    """
    entities = _detect_entities(text)
    slugs = _detect_metrics(text)

    # 1) 지역 → TRDAR (상권 키워드 발견 시)
    region_slug = None
    for e in entities:
        if e in ALIAS_LOCATION_TO_SLUG:
            region_slug = ALIAS_LOCATION_TO_SLUG[e]
            break
    trdar_cd = SLUG_TO_TRDAR.get(region_slug or "", None)

    # 2) 엔드포인트별 파라미터 생성
    links: List[str] = []
    for s in slugs:
        ep = METRICS_TO_ENDPOINT.get(s)
        if not ep:
            continue

        if s == "analytics/store-counts":
            params = {
                "trdar_cd": trdar_cd,
                "radius":  radius,
                "group_by": group_by,
                "limit":   limit,
            }

        elif s == "market/change-index":
            # trdar_cd / adstrd_cd / signgu_cd 중 하나, + yyq(선택)
            params = {
                "trdar_cd": trdar_cd,
                "adstrd_cd": adstrd_cd,
                "signgu_cd": signgu_cd,
                "yyq": yyq,
            }

        elif s == "stores/closures":
            # signgu_cd or adstrd_cd 必, + year(선택)
            params = {
                "adstrd_cd": adstrd_cd,
                "signgu_cd": signgu_cd,
                "year": year,
            }

        elif s == "industry/metrics":
            # trdar_cd 우선, 없으면 adstrd_cd > signgu_cd, + yyq(선택)
            params = {
                "trdar_cd": trdar_cd,
                "adstrd_cd": adstrd_cd,
                "signgu_cd": signgu_cd,
                "yyq": yyq,
            }

        elif s == "sales/estimates":
            # trdar_cd / adstrd_cd / signgu_cd 중 하나, + yyq(선택)
            params = {
                "trdar_cd": trdar_cd,
                "adstrd_cd": adstrd_cd,
                "signgu_cd": signgu_cd,
                "yyq": yyq,
            }

        elif s == "region/center":
            params = {"trdar_cd": trdar_cd}

        else:
            params = {}

        links.append(ep + _qs(params))

    return {
        "entities": entities,
        "slugs": slugs,
        "trdar_cd": trdar_cd,
        "links": links,  # ← 바로 GET 가능한 URL들
    }

def save_keywords_log(meeting: Meeting, source: str, raw_text: str, result: Dict[str, Any]) -> KeywordLog:
    return KeywordLog.objects.create(
        meeting=meeting, source=source, raw_text=raw_text,
        keywords=result, created_at=timezone.now(),
    )


# --- 호환용: minutes/views.py에서 기대하는 시그니처 복구 ---
# 기존 규칙과 동일하게: entities/intents는 LLM+룰 기반,
# metrics는 화이트리스트 canonical, api_hints는 slug 목록으로 반환.
_SLUG_TO_CANONICAL: Dict[str, str] = {m["slug"]: m["canonical"] for m in METRIC_CATALOG}

def extract_keywords_llm(text: str) -> Dict[str, Any]:
    """
    minutes/views.py 호환을 위한 래퍼.
    - 내부 규칙 기반으로 엔티티/메트릭을 추출
    - metrics: canonical 문자열 목록
    - api_hints: 실제 엔드포인트 슬러그 목록
    - intents: (필요시 확장) 지금은 빈 배열
    """
    # 1) 엔티티는 LLM + 사전 보강
    entities = _detect_entities(text)

    # 2) 메트릭은 화이트리스트 규칙으로만
    slugs = _detect_metrics(text)  # 예: ["analytics/store-counts", "industry/metrics"]
    metrics = [_SLUG_TO_CANONICAL.get(s, s) for s in slugs]  # canonical로 매핑

    # 3) intents는 현재 비워둠(필요하면 LLM 파싱 확장)
    intents: List[str] = []

    return {
        "entities": entities,
        "metrics": metrics,     # canonical
        "intents": intents,
        "api_hints": slugs,     # slug (실제 호출용 힌트)
    }
