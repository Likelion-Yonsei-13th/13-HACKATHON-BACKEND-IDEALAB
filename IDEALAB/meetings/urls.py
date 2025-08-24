from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MeetingViewSet, BlockViewSet, AttachmentViewSet

router = DefaultRouter()
router.register(r"meetings", MeetingViewSet, basename="meetings")
router.register(r"blocks", BlockViewSet, basename="blocks")
router.register(r"attachments", AttachmentViewSet, basename="attachments")

urlpatterns = [ path("", include(router.urls)), ]
