# analytics/views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Avg, Sum, Q

# services
from .services.region import get_trdar_center
from .services.store_radius import StoreRadiusClient, aggregate_counts
from .services.seoul_openapi import iter_industry_metrics

# 기존
# from .models import ChangeIndex, ClosureStat, IndustryMetric, SalesEstimate

# 변경
try:
    from .models import ChangeIndex, ClosureStat, IndustryMetric, SalesEstimate
except ImportError:
    ChangeIndex = ClosureStat = IndustryMetric = None  # 없으면 None
    SalesEstimate = None
    
# ------------------------------------------------------------------------------
# (옵션) 상권 중심좌표
@api_view(["GET"])
def region_center(request):
    trdar_cd = request.GET.get("trdar_cd")
    if not trdar_cd:
        return Response({"detail": "trdar_cd is required."}, status=400)
    cx, cy = get_trdar_center(trdar_cd)
    if cx is None or cy is None:
        return Response({"detail": "TRDAR not found."}, status=404)
    return Response({"cx": cx, "cy": cy})

# ------------------------------------------------------------------------------
# 문서 #1: 반경 내 점포 수 & 업종 분포 (/api/analytics/store-counts/)
@api_view(["GET"])
def store_counts(request):
    trdar_cd = request.GET.get("trdar_cd")
    cx_q = request.GET.get("cx")
    cy_q = request.GET.get("cy")
    radius_raw = request.GET.get("radius")
    group_by = request.GET.get("group_by")  # lcls|mcls|scls
    limit_raw = request.GET.get("limit")

    # radius 필수
    if not radius_raw:
        return Response({"status":400,"success":False,"message":"잘못된 요청: radius는 필수입니다.","data":None},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        radius = int(radius_raw); assert radius > 0
    except Exception:
        return Response({"status":400,"success":False,"message":"잘못된 요청: radius는 양의 정수여야 합니다.","data":None},
                        status=status.HTTP_400_BAD_REQUEST)

    if group_by and group_by not in ("lcls","mcls","scls"):
        return Response({"status":400,"success":False,"message":"잘못된 요청: group_by는 lcls/mcls/scls 중 하나여야 합니다.","data":None},
                        status=status.HTTP_400_BAD_REQUEST)

    limit = None
    if limit_raw:
        try:
            limit = int(limit_raw); assert limit > 0
        except Exception:
            return Response({"status":400,"success":False,"message":"잘못된 요청: limit는 양의 정수여야 합니다.","data":None},
                            status=status.HTTP_400_BAD_REQUEST)

    # 좌표 확보
    if cx_q and cy_q:
        try:
            cx, cy = float(cx_q), float(cy_q)
        except Exception:
            return Response({"status":400,"success":False,"message":"잘못된 요청: cx, cy는 숫자여야 합니다.","data":None},
                            status=status.HTTP_400_BAD_REQUEST)
    else:
        if not trdar_cd:
            return Response({"status":400,"success":False,"message":"잘못된 요청: trdar_cd 또는 (cx,cy) 중 하나는 반드시 필요합니다.","data":None},
                            status=status.HTTP_400_BAD_REQUEST)
        cx, cy = get_trdar_center(trdar_cd)
        if not cx or not cy:
            return Response({"status":404,"success":False,"message":"해당 상권을 찾을 수 없습니다.","data":None},
                            status=status.HTTP_404_NOT_FOUND)

    # 외부 상가업소 호출
    try:
        client = StoreRadiusClient()
        rows, total, _meta = client.fetch_all(cx=cx, cy=cy, radius=radius)
    except Exception as e:
        return Response({"status":502,"success":False,"message":"외부 상가업소 API 오류","data":{"reason":str(e)}},
                        status=status.HTTP_502_BAD_GATEWAY)

    # 그룹 집계(옵션)
    top_dict = None
    if group_by:
        l_map, m_map, s_map = aggregate_counts(rows)
        base = {"lcls": l_map, "mcls": m_map, "scls": s_map}[group_by]
        items = sorted(base.items(), key=lambda x: x[1], reverse=True)
        if limit:
            items = items[:limit]
        top_dict = dict(items)

    return Response({
        "status": 200, "success": True, "message": "상권 반경 내 점포 수 조회 성공",
        "params": {"trdar_cd": trdar_cd, "radius": radius, "group_by": group_by, "limit": limit, "cx": cx_q, "cy": cy_q},
        "data": {"total": total, "top": top_dict, "center": {"cx": cx, "cy": cy}}
    })

# ------------------------------------------------------------------------------
# 문서 #2: 상권 변화 지표 (/api/analytics/change-index/)
@api_view(["GET"])
def change_index(request):
    if ChangeIndex is None:
        return Response({"status":501,"success":False,"message":"ChangeIndex 모델이 없음"}, status=501)
    trdar_cd = request.GET.get("trdar_cd")
    signgu_cd = request.GET.get("signgu_cd")
    adstrd_cd = request.GET.get("adstrd_cd")
    yyq = request.GET.get("yyq")

    if not (trdar_cd or adstrd_cd or signgu_cd):
        return Response({"status":400,"success":False,"message":"trdar_cd/adstrd_cd/signgu_cd 중 하나는 필수","data":None},
                        status=400)

    # 우선순위: trdar_cd > adstrd_cd > signgu_cd
    q = Q()
    if trdar_cd:
        q &= Q(trdar_cd=trdar_cd)
    elif adstrd_cd:
        q &= Q(adstrd_cd=adstrd_cd)
    else:
        q &= Q(signgu_cd=signgu_cd)
    if yyq:
        q &= Q(yyq=yyq)

    rows = list(ChangeIndex.objects.filter(q).values(
        "trdar_cd","yyq","change_code","change_level","score"
    ))

    if not rows:
        return Response({"status":404,"success":False,"message":"데이터가 없습니다.","data":None}, status=404)

    avg_score = None
    try:
        avg_score = ChangeIndex.objects.filter(q).aggregate(avg=Avg("score"))["avg"]
    except Exception:
        pass

    return Response({
        "status":200, "success":True, "message":"상권변화지표 조회 성공",
        "params":{"trdar_cd":trdar_cd,"adstrd_cd":adstrd_cd,"signgu_cd":signgu_cd,"yyq":yyq},
        "region":{"trdars_count": len({r["trdar_cd"] for r in rows if r["trdar_cd"]})},
        "aggregate":{"change_index_avg": avg_score},
        "items": rows
    })

# ------------------------------------------------------------------------------
# 문서 #3: 폐업 통계 (/api/analytics/closures/)
@api_view(["GET"])
def closures(request):
    if ClosureStat is None:
        return Response({"status":501,"success":False,"message":"ClosureStat 모델이 없음"}, status=501)
    signgu_cd = request.GET.get("signgu_cd")
    adstrd_cd = request.GET.get("adstrd_cd")
    year = request.GET.get("year")

    if not (signgu_cd or adstrd_cd):
        return Response({"status":400,"success":False,"message":"signgu_cd 또는 adstrd_cd 중 하나는 필수","data":None},
                        status=400)

    q = Q()
    if adstrd_cd:
        q &= Q(adstrd_cd=adstrd_cd)
    else:
        q &= Q(signgu_cd=signgu_cd)
    if year:
        q &= Q(year=year)

    rows = list(ClosureStat.objects.filter(q).values())
    if not rows:
        return Response({"status":404,"success":False,"message":"대상 구간에 해당하는 데이터가 없습니다.","data":None}, status=404)

    total = sum(int(r.get("closures", 0)) for r in rows)  # 필드명은 모델에 맞춰 수정
    # 필요 시 지역명 조인
    region = {
        "signgu_cd": signgu_cd,
        "adstrd_cd": adstrd_cd,
    }

    return Response({
        "status":200, "success":True, "message":"폐업 통계 조회 성공",
        "params":{"signgu_cd":signgu_cd,"adstrd_cd":adstrd_cd,"year":year},
        "region": region,
        "items": rows,
        "aggregate": {"closures_sum": total}
    })

# ------------------------------------------------------------------------------
# 문서 #4: 산업 지표 종합 (/api/analytics/industry-metrics/)
@api_view(["GET"])
def industry_metrics(request):
    yyq = request.GET.get("yyq")  # e.g., "20241"
    trdar_cd = request.GET.get("trdar_cd") or None
    signgu_cd = request.GET.get("signgu_cd") or None
    adstrd_cd = request.GET.get("adstrd_cd") or None

    if not (trdar_cd or adstrd_cd or signgu_cd):
        return Response(
            {"status": 400, "success": False,
             "message": "trdar_cd/adstrd_cd/signgu_cd 중 하나는 필수",
             "data": None},
            status=400,
        )

    # 1) 단일 상권이면 외부 오픈API 요약본으로 즉시 응답 (DB 없이도 200)
    if trdar_cd:
        items = list(iter_industry_metrics(trdar=trdar_cd, year=yyq))
        agg = {}
        if items:
            def _num(x): 
                try: return int(x or 0)
                except: return 0
            agg = {
                "thsmon_selng_amt_sum": sum(_num(x.get("thsmon_selng_amt")) for x in items if isinstance(x, dict)),
                "thsmon_selng_co_sum":  sum(_num(x.get("thsmon_selng_co"))  for x in items if isinstance(x, dict)),
                "mdwk_selng_amt_sum":   sum(_num(x.get("mdwk_selng_amt"))   for x in items if isinstance(x, dict)),
                "wkend_selng_amt_sum":  sum(_num(x.get("wkend_selng_amt"))  for x in items if isinstance(x, dict)),
            }
        return Response({
            "status": 200, "success": True, "message": "상권 산업 지표 조회 성공(외부 API 요약본)",
            "params": {"trdar_cd": trdar_cd, "yyq": yyq},
            "region": {"trdars_count": 1, "trdars": [trdar_cd]},
            "aggregate": agg, "items": items,
        })

    # 2) 구/동 단위 → 내부 ETL 필요. 모델 없거나 데이터 없으면 안내
    try:
        from .models import IndustryMetric
    except Exception:
        return Response(
            {"status": 501, "success": False,
             "message": "IndustryMetric 모델이 없어 구/동 집계는 비활성화(ETL 필요)",
             "data": None},
            status=501,
        )

    q = Q()
    if adstrd_cd: q &= Q(adstrd_cd=adstrd_cd)
    else:         q &= Q(signgu_cd=signgu_cd)
    if yyq:       q &= Q(yyq=yyq)

    qs = IndustryMetric.objects.filter(q)
    if not qs.exists():
        return Response(
            {"status": 404, "success": False,
             "message": "대상 구간 데이터가 없습니다.",
             "data": None},
            status=404,
        )

    agg = qs.aggregate(
        thsmon_selng_amt_sum=Sum("thsmon_selng_amt"),
        thsmon_selng_co_sum=Sum("thsmon_selng_co"),
        mdwk_selng_amt_sum=Sum("mdwk_selng_amt"),
        wkend_selng_amt_sum=Sum("wkend_selng_amt"),
    )
    items = list(qs.values(
        "trdar_cd","yyq","svc_induty_cd","svc_induty_cd_nm",
        "thsmon_selng_amt","thsmon_selng_co","mdwk_selng_amt","wkend_selng_amt"
    ))

    return Response({
        "status": 200, "success": True, "message": "상권 산업 지표 조회 성공",
        "params": {"signgu_cd": signgu_cd, "adstrd_cd": adstrd_cd, "yyq": yyq, "trdar_cd": trdar_cd},
        "region": {"trdars_count": qs.values("trdar_cd").distinct().count(),
                   "trdars": list(qs.values_list("trdar_cd", flat=True).distinct()),
                   "signgu_cd": signgu_cd, "adstrd_cd": adstrd_cd},
        "aggregate": agg, "items": items
    })
# ------------------------------------------------------------------------------
# 문서 #5: 추정 매출 (/api/analytics/sales-estimates/)
@api_view(["GET"])
def sales_estimates(request):
    if SalesEstimate is None:
        return Response(
            {
                "status": 501,
                "success": False,
                "message": "SalesEstimate 모델이 없어 기능이 비활성화되어 있습니다. (ETL/모델 추가 필요)",
                "data": None,
            },
            status=501,
        )
    
    trdar_cd = request.GET.get("trdar_cd")
    signgu_cd = request.GET.get("signgu_cd")
    adstrd_cd = request.GET.get("adstrd_cd")
    yyq = request.GET.get("yyq")

    if not (trdar_cd or adstrd_cd or signgu_cd):
        return Response({"status":400,"success":False,"message":"trdar_cd/adstrd_cd/signgu_cd 중 하나는 필수","data":None},
                        status=400)

    q = Q()
    if trdar_cd:
        q &= Q(trdar_cd=trdar_cd)
    elif adstrd_cd:
        q &= Q(adstrd_cd=adstrd_cd)
    else:
        q &= Q(signgu_cd=signgu_cd)
    if yyq:
        q &= Q(yyq=yyq)

    qs = SalesEstimate.objects.filter(q)
    if not qs.exists():
        return Response({"status":404,"success":False,"message":"데이터가 없습니다.","data":None}, status=404)

    items = list(qs.values("trdar_cd","yyq","sales"))
    agg = qs.aggregate(sales_sum=Sum("sales"), sales_avg=Avg("sales"))

    return Response({
        "status":200,"success":True,"message":"상권 추정매출 조회 성공",
        "params":{"trdar_cd":trdar_cd,"signgu_cd":signgu_cd,"adstrd_cd":adstrd_cd,"yyq":yyq},
        "region":{"trdars_count": qs.values("trdar_cd").distinct().count()},
        "aggregate": {"sales_sum": agg["sales_sum"], "sales_avg": agg["sales_avg"]},
        "items": items
    })
