from django.db import models

class Meeting(models.Model):
    title         = models.CharField(max_length=200)
    project       = models.CharField(max_length=200, null=True, blank=True)
    market_area   = models.CharField(max_length=200, null=True, blank=True)
    scheduled_time= models.DateTimeField(null=True, blank=True)
    description   = models.TextField(null=True, blank=True)
    owner_id      = models.BigIntegerField()
    created_at    = models.DateTimeField(auto_now_add=True)
    ended_at      = models.DateTimeField(null=True, blank=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "meetings_meeting"
        ordering = ("-updated_at",)

class Block(models.Model):
    class BlockType(models.TextChoices):
        HEADING='heading','heading'
        PARAGRAPH='paragraph','paragraph'
        LIST='list','list'
        IMAGE='image','image'
        TABLE='table','table'
        QUOTE='quote','quote'
        CODE='code','code'

    meeting       = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="blocks")
    parent_block  = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    order_no      = models.IntegerField()
    type          = models.CharField(max_length=20, choices=BlockType.choices)
    level         = models.IntegerField(null=True, blank=True)
    text          = models.TextField(null=True, blank=True)
    rich_payload  = models.JSONField(null=True, blank=True)
    updated_by    = models.BigIntegerField(null=True, blank=True)
    updated_at    = models.DateTimeField(auto_now=True)
    # version 필드 제거됨

    class Meta:
        db_table = "meetings_block"
        indexes = [
            models.Index(fields=["meeting"]),
            models.Index(fields=["parent_block"]),
        ]

class BlockRevision(models.Model):
    block     = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="revisions")
    version   = models.IntegerField()  # 리비전 번호(1,2,3, …)
    snapshot  = models.JSONField()     # {type,level,text,rich_payload,order_no,parent_block}
    edited_by = models.BigIntegerField(null=True, blank=True)
    edited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meetings_block_revision"
        indexes = [models.Index(fields=["block"])]
        ordering = ("-edited_at", "id")

class Attachment(models.Model):
    meeting   = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="attachments")
    block     = models.ForeignKey(Block, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments")
    file_url  = models.TextField()
    mime_type = models.CharField(max_length=200, null=True, blank=True)
    size      = models.BigIntegerField(null=True, blank=True)
    created_at= models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meetings_attachment"
        indexes = [models.Index(fields=["meeting"])]
