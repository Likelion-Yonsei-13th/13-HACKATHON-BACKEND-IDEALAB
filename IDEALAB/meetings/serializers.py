from rest_framework import serializers
from .models import Meeting

class MeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = ["id", "title", "project", "market_area", "scheduled_time", "created_at"]

class MeetingCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    project = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    market_area = serializers.CharField(required=False, allow_blank=True, allow_null=True)
