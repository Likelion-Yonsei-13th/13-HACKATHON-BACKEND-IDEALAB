from django.db import models
from meetings.models import Meeting

class MinutesSnapshot(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE)
    is_final = models.BooleanField(default=False)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
