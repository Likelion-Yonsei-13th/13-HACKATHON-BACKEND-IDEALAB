# analytics/admin.py
from django.contrib import admin
from .models import TradingArea, IndustryMetric, ChangeIndex, ClosureStat

@admin.register(TradingArea)
class TradingAreaAdmin(admin.ModelAdmin):
    list_display = ("trdar_cd", "trdar_cd_nm", "signgu_cd_nm", "adstrd_cd_nm")
    search_fields = ("trdar_cd", "trdar_cd_nm", "signgu_cd_nm", "adstrd_cd_nm")

@admin.register(IndustryMetric)
class IndustryMetricAdmin(admin.ModelAdmin):
    list_display = ("trdar_cd", "yyq", "svc_induty_cd_nm", "thsmon_selng_amt")
    search_fields = ("trdar_cd", "yyq", "svc_induty_cd_nm")

@admin.register(ChangeIndex)
class ChangeIndexAdmin(admin.ModelAdmin):
    list_display = ("trdar_cd", "yyq", "change_index")
    search_fields = ("trdar_cd", "yyq")

@admin.register(ClosureStat)
class ClosureStatAdmin(admin.ModelAdmin):
    list_display = ("year", "signgu_cd_nm", "adstrd_cd_nm", "category", "closures")
    search_fields = ("signgu_cd_nm", "adstrd_cd_nm", "category")
