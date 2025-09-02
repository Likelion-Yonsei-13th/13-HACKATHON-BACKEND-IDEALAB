from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter
from .views import MeetingViewSet, BlockViewSet, AttachmentViewSet

# 최상위: meetings만 등록
router = DefaultRouter()
router.register(r"meetings", MeetingViewSet, basename="meetings")

# meetings/{meeting_pk}/blocks, meetings/{meeting_pk}/attachments
nested = NestedDefaultRouter(router, r"meetings", lookup="meeting")
nested.register(r"blocks", BlockViewSet, basename="meeting-blocks")
nested.register(r"attachments", AttachmentViewSet, basename="meeting-attachments")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(nested.urls)),
]
