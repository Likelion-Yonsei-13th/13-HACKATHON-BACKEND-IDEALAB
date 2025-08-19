from django.urls import path
from .views import MeetingListCreateView, MeetingDetailView

urlpatterns = [
    path("meetings/", MeetingListCreateView.as_view(), name="meetings-list-create"),
    path("meetings/<int:meeting_id>/", MeetingDetailView.as_view(), name="meetings-detail"),
]
