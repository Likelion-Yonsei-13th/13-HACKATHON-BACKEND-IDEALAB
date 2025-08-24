# keywords/services/rules.py
import os
import re
import json
from typing import Dict, Any, List, Set
from django.utils import timezone
from openai import OpenAI

from meetings.models import Meeting
from keywords.models import KeywordLog

# ── LLM 클라이언트
_client = None
def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

# (선택) 규칙 사전: 필요 없으면 비워도 됨
LOCATION_WORDS = ["신촌", "홍대", "강남", "건대", "잠실"]
INDUSTRY_WORDS = ["카페", "분식", "치킨", "편의점", "독서실", "피트니스"]

# ─────────────────────────────────────────────────────────────────────────────
# 제공 가능한 메트릭만 정의 (화이트리스트)
# canonical: 표준 표기(프론트/응답에 노출)
# slug: 실제 API 라우트 식별자(내부 용도)
# synonyms: 허용 동의어 (여기 있는 것만 매칭, 부분일치 X)

METRIC_CATALOG = [
    {
        "canonical": "상권 영역",
        "slug": "area/polygon",
        "synonyms": ["상권폴리곤", "상권 경계", "상권 경계선", "폴리곤", "지도 경계"],
    },
    {
        "canonical": "유동인구",
        "slug": "mobility/foot-traffic",
        "synonyms": ["생활인구", "유입인구", "유동량", "유동량지수", "유입량"],
    },
    {
        "canonical": "업종별 매출",
        "slug": "sales/by-industry",
        "synonyms": ["업종 매출", "카테고리 매출", "업종 매출액", "업종별 매출액"],
    },
    {
        "canonical": "점포 정보",
        "slug": "stores/info",
        "synonyms": ["점포현황", "상점 정보", "가게 정보", "점포 리스트", "상점 리스트"],
    },
    {
        "canonical": "업종 포화도(점포 수)",
        "slug": "stores/count",
        "synonyms": ["업종 포화도", "점포 수", "매장 수", "숍 카운트", "상점 수"],
    },
    {
        "canonical": "평균 임대료",
        "slug": "rent/avg",
        "synonyms": ["임대료", "월세", "보증금", "임차료", "임대비용", "평균월세"],
    },
    {
        "canonical": "도로상황",
        "slug": "road/conditions",
        "synonyms": ["도로 상황", "교통상황", "도로혼잡도", "교통량"],
    },
    {
        "canonical": "주차장",
        "slug": "parking/lots",
        "synonyms": ["주차", "주차 가능", "공영주차장", "민영주차장", "주차장 위치"],
    },
    {
        "canonical": "버스/지하철",
        "slug": "transit/bus-subway",
        "synonyms": ["대중교통", "지하철", "버스", "환승", "역세권", "정류장"],
    },
    {
        "canonical": "연세권 여부",
        "slug": "poi/university-zone",
        "synonyms": ["대학가", "대학 인접", "대학권", "캠퍼스 인접", "연세대 인접", "연세대 근처"],
    },
    {
        "canonical": "주변 시설(학교)·학생수",
        "slug": "poi/schools-students",
        "synonyms": ["학교 수", "학생 수", "초중고", "교육시설", "학령인구"],
    },
    {
        "canonical": "직장인 인구수(배후지)",
        "slug": "population/office-workers",
        "synonyms": ["직장인 수", "근로자 수", "직장인 인구", "배후지 인구", "오피스 인구"],
    },
    {
        "canonical": "공실률",
        "slug": "vacancy/rate",
        "synonyms": ["빈점포율", "공가율", "공실 비율"],
    },
    {
        "canonical": "평균 매출/성장률",
        "slug": "sales/avg-growth",
        "synonyms": ["매출 성장률", "평균 매출", "성장률", "전년대비 매출"],
    },
    {
        "canonical": "폐업률",
        "slug": "stores/closure-rate",
        "synonyms": ["폐업 비율", "업종 감소", "폐점률", "폐업 통계"],
    },
    {
        "canonical": "상권변화지표",
        "slug": "market/change-index",
        "synonyms": ["상권 변화", "상권 변화 지수", "상권 지표 변화", "상권추세"],
    },
    {
        "canonical": "네이버 검색 트렌드",
        "slug": "trends/naver-search",
        "synonyms": ["검색 트렌드", "네이버 트렌드", "검색량 추이", "키워드 트렌드"],
    },
]

# 허용 메트릭 빠른 조회용 인덱스 생성
_ALLOWED_CANONICAL: Set[str] = {m["canonical"] for m in METRIC_CATALOG}
# 동의어 → canonical 역매핑
_SYNONYM_TO_CANONICAL: Dict[str, str] = {}
for m in METRIC_CATALOG:
    for s in m.get("synonyms", []):
        _SYNONYM_TO_CANONICAL[s] = m["canonical"]

# canonical → slug 매핑
_CANONICAL_TO_SLUG: Dict[str, str] = {m["canonical"]: m["slug"] for m in METRIC_CATALOG}

# 정규식: 단어 경계 기반 한글/숫자 토큰 매칭
def _contains_token(text: str, token: str) -> bool:
    # 한글/숫자/영문 혼합을 안전하게 보기 위한 경계; 한국어는 공백 분절이 불완전하므로
    # 앞뒤 비한글/숫자/영문 경계 기준으로 근사 처리
    pattern = rf'(?<![가-힣0-9A-Za-z]){re.escape(token)}(?![가-힣0-9A-Za-z])'
    return re.search(pattern, text) is not None

def _normalize_metrics_from_text(text: str) -> Dict[str, Any]:
    """
    원문(text)에서 화이트리스트 기반으로만 메트릭 추출.
    - 정확 표기 또는 허용 동의어만 인정
    - 부분일치 금지(단어경계 사용)
    """
    found_canonicals: Set[str] = set()

    # 1) canonical 직접 탐지
    for canonical in _ALLOWED_CANONICAL:
        if _contains_token(text, canonical):
            found_canonicals.add(canonical)

    # 2) synonyms → canonical 승격
    for syn, canonical in _SYNONYM_TO_CANONICAL.items():
        if _contains_token(text, syn):
            found_canonicals.add(canonical)

    # api_hints는 발견된 canonical에 한해 제공
    metrics_sorted = sorted(found_canonicals)
    api_hints_sorted = sorted(_CANONICAL_TO_SLUG[c] for c in metrics_sorted)
    return {"metrics": metrics_sorted, "api_hints": api_hints_sorted}

LLM_SYSTEM = (
    "You are a keyword detector for a Korean startup workspace. "
    "Extract:\n"
    "1) entities: locations, industries, brand/product names\n"
    "2) metrics: business metrics (e.g., 임대료, 매출, 유동인구, 공실률, 상권지수)\n"
    "3) intents: user intents like '원룸 임대료 비교', '신촌 카페 창업', '상권 데이터 확인'\n"
    "Return strict JSON: {\"entities\":[], \"metrics\":[], \"intents\":[]}"
)

def extract_keywords_llm(text: str) -> Dict[str, Any]:
    """
    LLM으로 엔티티/의도만 받아오고,
    메트릭/API 힌트는 **화이트리스트 규칙**으로만 채운다.
    """
    client = get_client()
    # 1) LLM 호출 (엔티티/의도만 신뢰)
    entities: List[str] = []
    intents: List[str] = []
    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_KEYWORDS_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": LLM_SYSTEM},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        parsed = json.loads(raw)
        # LLM이 뱉은 metrics는 신뢰하지 않고, 화이트리스트 교차만 허용할 예정
        entities = list({e for e in parsed.get("entities", []) if isinstance(e, str)})
        intents  = list({i for i in parsed.get("intents", []) if isinstance(i, str)})
    except Exception as e:
        # LLM 실패해도 규칙 기반 메트릭 탐지는 진행
        entities, intents = [], []

    # 2) 규칙 보정: 엔티티(위치/업종) 추가 감지
    for w in LOCATION_WORDS + INDUSTRY_WORDS:
        if _contains_token(text, w):
            entities.append(w)
    entities = sorted(set(entities))

    # 3) 메트릭/API 힌트는 **화이트리스트 기반**으로만 도출
    metric_pack = _normalize_metrics_from_text(text)
    metrics = metric_pack["metrics"]
    api_hints = metric_pack["api_hints"]

    return {
        "entities": entities,
        "metrics": metrics,       # 화이트리스트 교차만
        "intents": intents,
        "api_hints": api_hints,   # 화이트리스트에 있는 것만
    }

def save_keywords_log(meeting: Meeting, source: str, raw_text: str, keywords: Dict[str, Any]) -> KeywordLog:
    return KeywordLog.objects.create(
        meeting=meeting,
        source=source,
        raw_text=raw_text,
        keywords=keywords,
        created_at=timezone.now(),
    )
