from rest_framework import serializers
from .models import Meeting, Block, BlockRevision, Attachment

class MeetingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = ("id","title","project","market_area","scheduled_time","description")

class MeetingSerializer(MeetingCreateSerializer):
    class Meta(MeetingCreateSerializer.Meta):
        fields = MeetingCreateSerializer.Meta.fields + ("owner_id","created_at","updated_at","ended_at")

class BlockCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Block
        fields = ("id","meeting","parent_block","order_no","type","level","text","rich_payload")

class BlockUpdateSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField()
    class Meta:
        model = Block
        fields = ("text","level","rich_payload","version")

class BlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Block
        fields = ("id","meeting","parent_block","order_no","type","level","text",
                  "rich_payload","updated_by","updated_at","version")

class BlockRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockRevision
        fields = ("id","block","version","snapshot","edited_by","edited_at")

class AttachmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = ("id","meeting","block","file_url","mime_type","size")

class AttachmentSerializer(AttachmentCreateSerializer):
    class Meta(AttachmentCreateSerializer.Meta):
        fields = AttachmentCreateSerializer.Meta.fields + ("created_at",)
