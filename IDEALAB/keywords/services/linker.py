# keywords/services/linker.py
from typing import Dict, Any, List
from django.db.models import Q

from analytics.models import TradingArea, StoreCount, IndustryMetric, ChangeIndex, ClosureStat

# 슬러그 → 백엔드 엔드포인트(라우트) 매핑
# 실제 analytics urls 구조에 맞게 여기만 조정하면 됨
SLUG_TO_ENDPOINT = {
    "area/polygon":           "/api/analytics/areas",
    "stores/count":           "/api/analytics/stores/count",
    "sales/by-industry":      "/api/analytics/sales/by-industry",
    "market/change-index":    "/api/analytics/change-index",
    "stores/closure-rate":    "/api/analytics/closures",
    # 필요시 계속 추가
}

def _find_trading_areas_by_entities(entities: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    """
    텍스트 엔티티(예: '신촌', '강남')로 상권 후보 찾아서 반환.
    """
    if not entities:
        return []

    qs = TradingArea.objects.none()
    for e in entities:
        qs = qs.union(
            TradingArea.objects.filter(
                Q(trdar_cd_nm__icontains=e) | Q(signgu_cd_nm__icontains=e) | Q(adstrd_cd_nm__icontains=e)
            ).only("trdar_cd", "trdar_cd_nm")[:limit]
        )

    # 중복 제거 & 상위 N만
    seen = set()
    results = []
    for ta in qs[:limit]:
        if ta.trdar_cd in seen:
            continue
        seen.add(ta.trdar_cd)
        results.append({"trdar_cd": ta.trdar_cd, "trdar_cd_nm": ta.trdar_cd_nm})
    return results

def _suggest_area_polygon(entities: List[str]) -> List[Dict[str, Any]]:
    endpoint = SLUG_TO_ENDPOINT["area/polygon"]
    items = []
    for ta in _find_trading_areas_by_entities(entities):
        items.append({
            "slug": "area/polygon",
            "endpoint": endpoint,
            "params": {"trdar": ta["trdar_cd"]},
            "label": f"{ta['trdar_cd_nm']} (상권 영역)",
        })
    return items

def _suggest_store_counts(entities: List[str]) -> List[Dict[str, Any]]:
    endpoint = SLUG_TO_ENDPOINT["stores/count"]
    items = []
    for ta in _find_trading_areas_by_entities(entities):
        # 기본 반경 2000으로 제안
        items.append({
            "slug": "stores/count",
            "endpoint": endpoint,
            "params": {"trdar": ta["trdar_cd"], "radius": 2000},
            "label": f"{ta['trdar_cd_nm']} 업종 포화도(점포 수)",
        })
    return items

def _suggest_sales_by_industry(entities: List[str]) -> List[Dict[str, Any]]:
    endpoint = SLUG_TO_ENDPOINT["sales/by-industry"]
    items = []
    for ta in _find_trading_areas_by_entities(entities):
        # 업종명 리스트 간단 추천(많이 등장한 업종 우선)
        # 너무 비싸지 않도록 distinct + 상위 몇 개만
        svc_names = (
            IndustryMetric.objects
            .filter(trdar_cd=ta["trdar_cd"])
            .exclude(svc_induty_cd=None)
            .values_list("svc_induty_cd_nm", flat=True)
            .distinct()[:5]
        )
        if svc_names:
            for nm in svc_names:
                items.append({
                    "slug": "sales/by-industry",
                    "endpoint": endpoint,
                    "params": {"trdar": ta["trdar_cd"], "industry_name": nm},
                    "label": f"{ta['trdar_cd_nm']} – {nm} 업종별 매출",
                })
        else:
            # 업종 후보가 아직 없으면 상권만으로 제안
            items.append({
                "slug": "sales/by-industry",
                "endpoint": endpoint,
                "params": {"trdar": ta["trdar_cd"]},
                "label": f"{ta['trdar_cd_nm']} 업종별 매출",
            })
    return items

def _suggest_change_index(entities: List[str]) -> List[Dict[str, Any]]:
    endpoint = SLUG_TO_ENDPOINT["market/change-index"]
    items = []
    for ta in _find_trading_areas_by_entities(entities):
        # 최신 분기 하나 잡아서 미리보기 파라미터 제안
        latest = (
            ChangeIndex.objects
            .filter(trdar_cd=ta["trdar_cd"])
            .order_by("-yyq")
            .values_list("yyq", flat=True)
            .first()
        )
        params = {"trdar": ta["trdar_cd"]}
        if latest:
            params["yyq"] = latest
        items.append({
            "slug": "market/change-index",
            "endpoint": endpoint,
            "params": params,
            "label": f"{ta['trdar_cd_nm']} 상권변화지표",
        })
    return items

def _suggest_closures(entities: List[str]) -> List[Dict[str, Any]]:
    """
    엔티티(예: '강남', '신촌')와 매칭되는 상권의 자치구/행정동 코드를 찾아
    /api/analytics/closures 에 바로 때려 넣을 수 있는 파라미터를 제안한다.
    - 기본: 자치구 기준(signgu_cd)로 제안
    - year는 DB에 있는 가장 최신 연도 사용(없으면 2023 기본)
    """
    endpoint = SLUG_TO_ENDPOINT["stores/closure-rate"]
    items: List[Dict[str, Any]] = []

    # 최신 연도 하나 잡기 (없으면 2023)
    latest_year = (
        ClosureStat.objects.order_by("-year").values_list("year", flat=True).first()
        or 2023
    )

    for ta in _find_trading_areas_by_entities(entities):
        # 해당 상권의 자치구 코드 우선
        ta_row = TradingArea.objects.filter(trdar_cd=ta["trdar_cd"]).only("signgu_cd", "signgu_cd_nm", "adstrd_cd", "adstrd_cd_nm").first()
        if not ta_row:
            continue

        if getattr(ta_row, "signgu_cd", None):
            items.append({
                "slug": "stores/closure-rate",
                "endpoint": endpoint,
                "params": {"signgu_cd": ta_row.signgu_cd, "year": latest_year},
                "label": f"{ta.get('trdar_cd_nm') or ''} – {getattr(ta_row, 'signgu_cd_nm', '')} 폐업 통계",
            })
        elif getattr(ta_row, "adstrd_cd", None):
            items.append({
                "slug": "stores/closure-rate",
                "endpoint": endpoint,
                "params": {"adstrd_cd": ta_row.adstrd_cd, "year": latest_year},
                "label": f"{ta.get('trdar_cd_nm') or ''} – {getattr(ta_row, 'adstrd_cd_nm', '')} 폐업 통계",
            })

    return items

# 슬러그 → 제안 함수 라우팅
_BUILDERS = {
    "area/polygon":        _suggest_area_polygon,
    "stores/count":        _suggest_store_counts,
    "sales/by-industry":   _suggest_sales_by_industry,
    "market/change-index": _suggest_change_index,
    "stores/closure-rate": _suggest_closures,

}

def build_api_suggestions(entities: List[str], api_hints: List[str]) -> List[Dict[str, Any]]:
    """
    키워드 추출 결과(entities, api_hints)로, 프론트에서 바로 호출 가능한
    백엔드 API “제안 목록”을 만들어 반환.
    각 항목: { slug, endpoint, params, label }
    """
    suggestions: List[Dict[str, Any]] = []

    # api_hints 에 포함된 슬러그만 처리 (화이트리스트 성격)
    for slug in api_hints:
        builder = _BUILDERS.get(slug)
        if not builder:
            continue
        try:
            suggestions.extend(builder(entities))
        except Exception:
            # 일부 실패해도 전체는 계속
            continue

    # 중복 제거(같은 endpoint+params 조합)
    dedup = []
    seen = set()
    for s in suggestions:
        key = (s["slug"], s["endpoint"], tuple(sorted(s["params"].items())))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(s)
    return dedup

