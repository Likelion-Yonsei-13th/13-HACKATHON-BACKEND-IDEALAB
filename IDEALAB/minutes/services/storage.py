from django.utils import timezone
from minutes.models import MinutesSnapshot
from .merger import merge_minutes

def save_live_minutes(meeting, new_minutes_json):
    latest = MinutesSnapshot.objects.filter(meeting=meeting, is_final=False).order_by("-id").first()
    merged = merge_minutes(latest.payload, new_minutes_json) if latest else new_minutes_json
    snap = MinutesSnapshot.objects.create(meeting=meeting, is_final=False, payload=merged)
    return snap.payload

def save_final_minutes(meeting, final_minutes_json):
    MinutesSnapshot.objects.filter(meeting=meeting, is_final=True).delete()
    snap = MinutesSnapshot.objects.create(meeting=meeting, is_final=True, payload=final_minutes_json)
    meeting.ended_at = timezone.now()
    meeting.save(update_fields=["ended_at"])
    return snap.payload
