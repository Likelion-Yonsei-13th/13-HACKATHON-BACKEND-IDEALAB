from rest_framework.views import APIView
from rest_framework.response import Response
from collections import Counter
from rest_framework import status
from django.db.models import Sum, Avg, Q
from .models import IndustryMetric, ChangeIndex, ClosureStat, TradingArea, StoreCount
from .serializers import IndustryMetricResponseSerializer, ChangeIndexResponseSerializer, ClosuresResponseSerializer


from .utils import parse_region_params, filter_trading_areas_by_region, parse_period_params

SCORE_MAP = {
    "HH": 3, "HL": 2, "LH": 1, "LL": 0,
    "다이나믹": 3, "성장": 2, "정체": 1, "쇠퇴": 0,
}

# 공통 에러 응답
def _fail(message: str, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({
        "status": http_status,
        "success": False,
        "message": message,
        "data": None
    }, status=http_status)


class IndustryMetricsByRegionView(APIView):
    """
    GET /api/analytics/industry-metrics/?adstrd_cd=11680580&yyq=2024Q4
    또는 GET /api/analytics/industry-metrics/?trdar_cd=3110023&yyq=2024Q4

    - TradingArea를 자치구/행정동으로 필터 → 해당 trdar_cd들의 IndustryMetric 조회
    - 집계는 매출 금액/건수 합계 중심(요약)
    - 응답: items(행 단위) + aggregate(합계)
    """
    def get(self, request):
        signgu_cd, adstrd_cd = parse_region_params(request)
        yyq, year = parse_period_params(request)  # year는 선택. 있으면 yyq를 만들어 사용.
        trdar_cd = request.query_params.get("trdar_cd")

        # yyq 우선, year만 왔으면 yyq로 치환(예: 2024 + Q4 필요하면 프런트에서 쿼리로 넘겨주세요)
        if not yyq and not year:
            return _fail("쿼리 파라미터가 누락되었습니다: yyq 또는 year 중 하나는 필수입니다.", status.HTTP_400_BAD_REQUEST)
        if not yyq and year:
            return _fail("현재 모델은 yyq(예: 2024Q4) 기준입니다. year만 주신 경우 yyq로 변환해 주세요.", status.HTTP_400_BAD_REQUEST)

        # 상권코드 직접 지정이 가장 정확
        if trdar_cd:
            trdars = [trdar_cd]
        else:
            ta_qs = filter_trading_areas_by_region(TradingArea, signgu_cd, adstrd_cd)
            trdars = list(ta_qs.values_list("trdar_cd", flat=True))

        if not trdars:
            return _fail("해당 지역에 매핑된 상권(TRDAR)이 없습니다.", status.HTTP_404_NOT_FOUND)

        qs = IndustryMetric.objects.filter(trdar_cd__in=trdars, yyq=yyq)
        if not qs.exists():
            return _fail("해당 기간(yyq)에 데이터가 없습니다.", status.HTTP_404_NOT_FOUND)

        # 원자료 rows (필요 컬럼만)
        items = list(qs.values(
            "trdar_cd", "yyq",
            "svc_induty_cd", "svc_induty_cd_nm",
            "thsmon_selng_amt", "thsmon_selng_co",
            "mdwk_selng_amt", "wkend_selng_amt",
        ))

        # 합계 집계
        agg = qs.aggregate(
            thsmon_selng_amt_sum=Sum("thsmon_selng_amt"),
            thsmon_selng_co_sum=Sum("thsmon_selng_co"),
            mdwk_selng_amt_sum=Sum("mdwk_selng_amt"),
            wkend_selng_amt_sum=Sum("wkend_selng_amt"),
        )

        resp = {
            "status": 200,
            "success": True,
            "message": "업종 지표 조회 성공",
            "params": {"signgu_cd": signgu_cd, "adstrd_cd": adstrd_cd, "yyq": yyq, "trdar_cd": trdar_cd},
            "region": {
                "trdars_count": len(trdars),
                "trdars": trdars[:50],  # 너무 길면 절단
                "signgu_cd": signgu_cd,
                "adstrd_cd": adstrd_cd,
            },
            "aggregate": agg,
            "items": items,
        }
        return Response(resp, status=status.HTTP_200_OK)


class ChangeIndexByRegionView(APIView):
    def get(self, request):
        signgu_cd, adstrd_cd = parse_region_params(request)
        yyq, _ = parse_period_params(request)
        if not yyq:
            return _fail("쿼리 파라미터가 누락되었습니다: yyq(예: 2023Q4)는 필수입니다.", status.HTTP_400_BAD_REQUEST)

        trdar_cd = request.query_params.get("trdar_cd")
        if trdar_cd:
            trdars = [trdar_cd]
        else:
            trdars = list(
                filter_trading_areas_by_region(TradingArea, signgu_cd, adstrd_cd)
                .values_list("trdar_cd", flat=True)
            )
        if not trdars:
            return _fail("해당 지역에 매핑된 상권(TRDAR)이 없습니다.", status.HTTP_404_NOT_FOUND)

        qs = ChangeIndex.objects.filter(trdar_cd__in=trdars, yyq=yyq)
        if not qs.exists():
            return _fail("해당 기간(yyq)에 데이터가 없습니다.", status.HTTP_404_NOT_FOUND)

        items = []
        scores = []
        for obj in qs.iterator():
            raw = (obj.raw_data or {}).get("snake", {})
            code = raw.get("상권_변화_지표")  # HH/HL/LH/LL
            level = obj.change_level
            # level이 없으면 코드로 한글 레벨 유추
            if not level and code in ("HH","HL","LH","LL"):
                level = {"HH":"쇠퇴","HL":"정체","LH":"성장","LL":"다이나믹"}.get(code)

            score = None
            if level in SCORE_MAP:
                score = SCORE_MAP[level]
            elif code in SCORE_MAP:
                score = SCORE_MAP[code]

            if score is not None:
                scores.append(score)

            items.append({
                "trdar_cd": obj.trdar_cd,
                "yyq": obj.yyq,
                "change_code": code,
                "change_level": level,
                "score": score,
            })

        agg_avg = sum(scores)/len(scores) if scores else None

        resp = {
            "status": 200,
            "success": True,
            "message": "상권변화지표 조회 성공",
            "params": {"signgu_cd": signgu_cd, "adstrd_cd": adstrd_cd, "yyq": yyq, "trdar_cd": trdar_cd},
            "region": {
                "trdars_count": len(trdars),
                "signgu_cd": signgu_cd, "adstrd_cd": adstrd_cd
            },
            "aggregate": {"change_index_avg": agg_avg},
            "items": items,
        }
        return Response(resp, status=status.HTTP_200_OK)


class ClosuresByRegionView(APIView):
    """
    GET /api/analytics/closures/?signgu_cd=11740&year=2023
    또는
    GET /api/analytics/closures/?signgu_nm=강동구&year=2023
    """
    def get(self, request):
        signgu_cd = request.GET.get("signgu_cd")
        signgu_nm = request.GET.get("signgu_nm")
        year = request.GET.get("year")

        if not year:
            return Response({
                "status": 400,
                "success": False,
                "message": "year 파라미터는 필수입니다.",
                "data": None,
            }, status=status.HTTP_400_BAD_REQUEST)
        qs = ClosureStat.objects.filter(year=year)
        if signgu_cd:
            qs = qs.filter(signgu_cd=signgu_cd)
        elif signgu_nm:
            qs = qs.filter(signgu_cd_nm=signgu_nm)

        items = list(qs.values("category", "closures"))

        # ✅ 집계 계산 로직 수정
        # 1) '전체' 행이 있으면 그 값을 총합으로 사용 (이중합 방지)
        total_row = qs.filter(category="전체").values_list("closures", flat=True).first()

        # 2) 없으면 '전체/합계' 같은 요약행을 제외하고 합계
        leaf_qs = qs.exclude(category__in=["전체", "합계"])
        leaf_sum = leaf_qs.aggregate(closures_sum=Sum("closures"))["closures_sum"]

        total_closures = total_row if total_row is not None else (leaf_sum or 0)

        resp = {
            "status": 200,
            "success": True,
            "message": "폐업 통계 조회 성공",
            "params": {"signgu_cd": signgu_cd, "signgu_nm": signgu_nm, "year": year},
            "region": {
                "signgu_cd": signgu_cd,
                "signgu_cd_nm": qs.values_list("signgu_cd_nm", flat=True).first(),
            },
            "items": items,
            "aggregate": {
                "closures_sum": total_closures,  # ⬅️ 이제 3023으로 나와요
            },
        }
        return Response(resp, status=status.HTTP_200_OK)
    
class StoreCountsView(APIView):
    """
    GET /api/analytics/store-counts/?trdar_cd=3110008&radius=2000
    """
    def get(self, request):
        trdar_cd = request.GET.get("trdar_cd")
        radius = request.GET.get("radius")

        if not trdar_cd or not radius:
            return Response(
                {"status": 400, "success": False, "message": "trdar_cd, radius는 필수입니다.", "data": None},
                status=400,
            )

        try:
            radius = int(radius)
        except ValueError:
            return Response(
                {"status": 400, "success": False, "message": "radius는 정수여야 합니다.", "data": None},
                status=400,
            )

        try:
            obj = StoreCount.objects.get(trdar_cd=trdar_cd, radius=radius)
        except StoreCount.DoesNotExist:
            return Response(
                {"status": 404, "success": False, "message": "해당 상권/반경 데이터 없음.", "data": None},
                status=404,
            )

        return Response({
            "status": 200,
            "success": True,
            "message": "상권 반경 내 점포 수 조회 성공",
            "params": {"trdar_cd": trdar_cd, "radius": radius},
            "data": {
                "total": obj.total,
                "center": {"cx": obj.cx, "cy": obj.cy},
                "raw": obj.raw_data,
            }
        }, status=200)
    
class StoreCountsByRadiusView(APIView):
    """
    GET /api/analytics/store-counts/?trdar_cd=3110008&radius=2000&group_by=mcls&limit=10
    - group_by: lcls(대분류) | mcls(중분류, 기본) | scls(소분류)
    - limit: 상위 N개 (기본 10)
    """
    def get(self, request):
        trdar_cd = request.GET.get("trdar_cd")
        radius = int(request.GET.get("radius", 2000))
        group_by = request.GET.get("group_by", "mcls")  # lcls|mcls|scls
        limit = int(request.GET.get("limit", 10))

        if not trdar_cd:
            return Response({
                "status": 400, "success": False,
                "message": "trdar_cd 파라미터는 필수입니다.", "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        obj = StoreCount.objects.filter(trdar_cd=trdar_cd, radius=radius).first()
        if not obj:
            return Response({
                "status": 404, "success": False,
                "message": "해당 상권/반경의 집계가 없습니다. fetch_store_counts를 먼저 실행하세요.",
                "data": None
            }, status=status.HTTP_404_NOT_FOUND)

        # ✓ 저장된 집계 사용
        if group_by == "lcls":
            counts = obj.counts_lcls or {}
        elif group_by == "scls":
            counts = obj.counts_scls or {}
        else:  # mcls (default)
            counts = obj.counts_mcls or {}

        # 상위 N개
        top_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        top_dict = {k: v for k, v in top_items}

        # 백업: 저장된 집계가 없으면 raw_data(샘플 20개)로라도 간이 집계
        if not top_dict and obj.raw_data:
            items = ((obj.raw_data or {}).get("body") or {}).get("items") or []
            key_map = {"lcls": "indsLclsNm", "mcls": "indsMclsNm", "scls": "indsSclsNm"}
            key = key_map.get(group_by, "indsMclsNm")
            cnt = Counter(it.get(key) for it in items if it.get(key))
            top_dict = dict(cnt.most_common(limit))

        return Response({
            "status": 200,
            "success": True,
            "message": "상권 반경 내 점포 수 조회 성공",
            "params": {"trdar_cd": trdar_cd, "radius": radius, "group_by": group_by, "limit": limit},
            "data": {
                "total": obj.total,
                "top": top_dict,     # ✅ 여기!
                "center": {"cx": obj.cx, "cy": obj.cy},
            }
        }, status=status.HTTP_200_OK)
