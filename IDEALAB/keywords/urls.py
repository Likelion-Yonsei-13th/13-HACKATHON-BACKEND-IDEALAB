from django.urls import path
from .views import ExtractKeywordsView, ListKeywordLogsView

urlpatterns = [
    path("meetings/<int:meeting_id>/keywords/extract/", ExtractKeywordsView.as_view()),
    path("meetings/<int:meeting_id>/keywords/", ListKeywordLogsView.as_view()),
]
