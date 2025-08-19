from django.db import models

class Meeting(models.Model):
    title = models.CharField(max_length=200)
    project = models.CharField(max_length=200, blank=True, default="")
    market_area = models.CharField(max_length=200, blank=True, default="")
    scheduled_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"[{self.id}] {self.title}"
