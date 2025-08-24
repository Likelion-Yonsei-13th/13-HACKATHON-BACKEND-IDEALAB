from django.urls import path
from .views import GetLiveMinutesView, GetFinalMinutesView, FinalizeView

urlpatterns = [
    path("meetings/<int:meeting_id>/minutes/live/", GetLiveMinutesView.as_view()),
    path("meetings/<int:meeting_id>/minutes/final/", GetFinalMinutesView.as_view()),
    path("meetings/<int:meeting_id>/finalize/", FinalizeView.as_view()),
]