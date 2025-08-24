from django.db import models
from django.db.models import JSONField
from meetings.models import Meeting

class KeywordLog(models.Model):
    SOURCE_CHOICES = [
        ("realtime", "Realtime"),
        ("final", "Final"),
    ]
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="keyword_logs")
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES)
    raw_text = models.TextField()  # 추출 기반 원문(청크/전체)
    keywords = models.JSONField()         # 예: {"entities":[...], "intents":[...], "api_hints":[...]}
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
