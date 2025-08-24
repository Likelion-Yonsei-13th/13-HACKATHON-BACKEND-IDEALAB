from django.urls import path
from .views import (
    IndustryMetricsByRegionView,
    ChangeIndexByRegionView,
    ClosuresByRegionView,
    StoreCountsView,
    StoreCountsByRadiusView,
)

urlpatterns = [
    path("analytics/industry-metrics/", IndustryMetricsByRegionView.as_view()),
    path("analytics/change-index/", ChangeIndexByRegionView.as_view()),
    path("analytics/closures/", ClosuresByRegionView.as_view()),
    path("analytics/store-counts/", StoreCountsByRadiusView.as_view()),
]
