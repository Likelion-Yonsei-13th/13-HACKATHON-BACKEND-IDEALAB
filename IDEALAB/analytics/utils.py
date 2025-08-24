from typing import Optional, Tuple
from django.db.models import QuerySet

def parse_region_params(request) -> Tuple[Optional[str], Optional[str]]:
    """
    ?signgu_cd= & ?adstrd_cd=
    - adstrd_cd 가 오면 최우선 (더 좁은 범위)
    - 둘 다 없으면 None, None
    """
    signgu_cd = (request.GET.get("signgu_cd") or "").strip() or None
    adstrd_cd = (request.GET.get("adstrd_cd") or "").strip() or None
    return signgu_cd, adstrd_cd


def filter_trading_areas_by_region(TradingArea, signgu_cd: Optional[str], adstrd_cd: Optional[str]) -> QuerySet:
    qs = TradingArea.objects.all()
    if adstrd_cd:
        qs = qs.filter(adstrd_cd=adstrd_cd)
    elif signgu_cd:
        qs = qs.filter(signgu_cd=signgu_cd)
    # else: 전체
    return qs


def parse_period_params(request):
    """
    업종 매출/변화지표:
      - ?yyq=2023Q4 (권장)  또는 ?year=2023
    폐업 통계:
      - ?year=2023 (필수)
    """
    yyq = (request.GET.get("yyq") or "").strip() or None
    year = request.GET.get("year")
    year = int(year) if (year and year.isdigit()) else None
    return yyq, year
