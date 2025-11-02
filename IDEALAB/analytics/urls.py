# analytics/urls.py
from django.urls import path
from .views import (
    region_center,           # 선택: rules에서 좌표가 필요하면 같이 씀
    store_counts,
    change_index,
    closures,
    industry_metrics,
    sales_estimates,
)

urlpatterns = [
    # 선택: 좌표 필요하면 사용 (문서에 없지만 rules가 씀)
    path("region/center/", region_center),

    # 문서 1
    path("store-counts/", store_counts),

    # 문서 2
    path("change-index/", change_index),

    # 문서 3
    path("closures/", closures),

    # 문서 4
    path("industry-metrics/", industry_metrics),

    # 문서 5
    path("sales-estimates/", sales_estimates),
]
