# analytics/models.py
from django.db import models

class TradingArea(models.Model):
    """
    상권(소권역) 마스터 — 이미 DB에 있다면 그대로 쓰면 됩니다.
    여기서는 CSV로도 입력 가능하도록 유지합니다.
    """
    trdar_cd = models.CharField(max_length=20, primary_key=True)   # 예: "3110023" 또는 "T3110023"
    trdar_cd_nm = models.CharField(max_length=255, blank=True, null=True)
    trdar_se_cd = models.CharField(max_length=10, blank=True, null=True)
    trdar_se_cd_nm = models.CharField(max_length=50, blank=True, null=True)
    x = models.FloatField(blank=True, null=True)
    y = models.FloatField(blank=True, null=True)
    signgu_cd = models.CharField(max_length=10, blank=True, null=True)      # 자치구코드
    signgu_cd_nm = models.CharField(max_length=50, blank=True, null=True)   # 자치구명
    adstrd_cd = models.CharField(max_length=20, blank=True, null=True)      # 행정동코드
    adstrd_cd_nm = models.CharField(max_length=50, blank=True, null=True)   # 행정동명
    area_m2 = models.FloatField(blank=True, null=True)

    class Meta:
        db_table = "analytics_trading_area"

    def __str__(self):
        return f"{self.trdar_cd_nm or self.trdar_cd}"


class IndustryMetric(models.Model):
    """
    업종/상권 단위의 분기 매출 지표 (CSV)
    - yyq: '2023Q4' 형식
    - 업종 필터가 없다면 SVC_INDUTY_CD_NM='전체' 같은 행만 적재해도 OK
    """
    trdar_cd = models.CharField(max_length=20, db_index=True)
    yyq = models.CharField(max_length=7, db_index=True)  # 예: 2023Q4
    svc_induty_cd = models.CharField(max_length=10, blank=True, null=True)
    svc_induty_cd_nm = models.CharField(max_length=100, blank=True, null=True)

    # 매출 금액/건수(전부 nullable)
    thsmon_selng_amt = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    thsmon_selng_co  = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    # 요일/시간대/성별/연령대 등 필요한 만큼 CSV 칼럼을 추가해도 됨
    # 예시(선택):
    mdwk_selng_amt = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    wkend_selng_amt = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)


    class Meta:
        db_table = "analytics_industry_metric"
        unique_together = (("trdar_cd", "yyq", "svc_induty_cd"),)


class ChangeIndex(models.Model):
    """
    상권변화지표 (CSV) — 상권 단위 분기 인덱스
    """
    trdar_cd = models.CharField(max_length=20, db_index=True)
    yyq = models.CharField(max_length=7, db_index=True)
    change_index = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    change_level = models.CharField(max_length=32, null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)


    # 필요시 세부 인덱스 컬럼 더 추가
    class Meta:
        db_table = "analytics_change_index"
        unique_together = (("trdar_cd", "yyq"),)


class ClosureStat(models.Model):
    """
    폐업 통계 (CSV) — 보유한 CSV가 자치구 기준이면 signgu 단위로 저장
    행정동 CSV가 있으면 adstrd 단위로도 저장 가능
    """
    year = models.IntegerField(db_index=True)
    signgu_cd = models.CharField(max_length=10, blank=True, null=True, db_index=True)
    signgu_cd_nm = models.CharField(max_length=50, blank=True, null=True)
    adstrd_cd = models.CharField(max_length=10, blank=True, null=True, db_index=True)
    adstrd_cd_nm = models.CharField(max_length=50, blank=True, null=True)

    category = models.CharField(max_length=50)  # 예: '음식', '서비스', '소매' 등 CSV 컬럼 기준
    closures = models.IntegerField(null=True, blank=True)  # 폐업 점포 수

    raw_data = models.JSONField(default=dict, blank=True)


    class Meta:
        db_table = "analytics_closure_stat"
        indexes = [
            models.Index(fields=["year", "signgu_cd"]),
            models.Index(fields=["year", "adstrd_cd"]),
        ]

class StoreRadiusStat(models.Model):
    """
    상권 중심좌표 기준 반경 내 업소 개수(업종별) 집계
    - 서울 상권분석서비스 'storeListInRadius'를 사용해 수집
    - radius(m) 단위. 기본 2000m.
    """
    trdar_cd = models.CharField(max_length=10, db_index=True)
    trdar_cd_nm = models.CharField(max_length=100, blank=True, null=True)

    # 참조용 (TradingArea snapshot)
    signgu_cd = models.CharField(max_length=10, blank=True, null=True, db_index=True)
    adstrd_cd = models.CharField(max_length=10, blank=True, null=True, db_index=True)
    x = models.IntegerField()  # WTM X
    y = models.IntegerField()  # WTM Y

    radius = models.IntegerField(default=2000, db_index=True)

    # 총 개수 및 업종별 개수
    total = models.IntegerField(default=0)
    counts_lcls = models.JSONField(default=dict, blank=True)  # 대분류명/코드별 카운트
    counts_mcls = models.JSONField(default=dict, blank=True)  # 중분류
    counts_scls = models.JSONField(default=dict, blank=True)  # 소분류

    # 원시 응답 일부 메타
    fetched_at = models.DateTimeField(auto_now=True)
    raw_meta = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "analytics_store_radius_stat"
        unique_together = (("trdar_cd", "radius"),)

class StoreCount(models.Model):
    trdar_cd = models.CharField(max_length=10, db_index=True)
    radius = models.IntegerField(default=2000)
    total = models.IntegerField(default=0)
    cx = models.FloatField(null=True, blank=True)  # WGS84 lon
    cy = models.FloatField(null=True, blank=True)  # WGS84 lat
    raw_data = models.JSONField(default=dict, blank=True)

    counts_lcls = models.JSONField(default=dict, blank=True)  # 대분류(indsLclsNm)
    counts_mcls = models.JSONField(default=dict, blank=True)  # 중분류(indsMclsNm)
    counts_scls = models.JSONField(default=dict, blank=True)  # 소분류(indsSclsNm)

    class Meta:
        db_table = "analytics_store_count"
        indexes = [
            models.Index(fields=["trdar_cd", "radius"]),
        ]
        unique_together = ("trdar_cd", "radius")
