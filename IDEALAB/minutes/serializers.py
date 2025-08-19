from rest_framework import serializers

class FinalizeSerializer(serializers.Serializer):
    project = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    market_area = serializers.CharField(required=False, allow_blank=True, allow_null=True)
