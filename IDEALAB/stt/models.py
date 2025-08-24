from django.db import models

class TranscriptSegment(models.Model):
    meeting = models.ForeignKey(
        "meetings.Meeting", on_delete=models.CASCADE, related_name="segments"
    )
    start_ms = models.IntegerField()
    end_ms = models.IntegerField()
    speaker = models.CharField(max_length=50, blank=True, default="")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
