from django.urls import path
from .views import STTChunkView

urlpatterns = [
    path("meetings/<int:meeting_id>/stt-chunk/", STTChunkView.as_view()),
]
