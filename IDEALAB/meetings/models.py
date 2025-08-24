from django.db import models

class Meeting(models.Model):
    title         = models.CharField(max_length=200)              # 회의 제목
    project       = models.CharField(max_length=200, null=True, blank=True)     # 프로젝트명(선택)
    market_area   = models.CharField(max_length=200, null=True, blank=True)     # 상권/시장 추천값
    scheduled_time= models.DateTimeField(null=True, blank=True)   # 회의 일시
    description   = models.TextField(null=True, blank=True)       # 본문(간략 소개)
    owner_id      = models.BigIntegerField()                      # 소유자 ID (추후 FK 권장)
    created_at    = models.DateTimeField(auto_now_add=True)       # 생성 일시
    ended_at      = models.DateTimeField(null=True, blank=True)   # 종료 일시
    updated_at    = models.DateTimeField(auto_now=True)           # 수정 일시

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
    order_no      = models.IntegerField()                          # 같은 parent 내 정렬
    type          = models.CharField(max_length=20, choices=BlockType.choices)
    level         = models.IntegerField(null=True, blank=True)     # 제목 레벨/리스트 depth
    text          = models.TextField(null=True, blank=True)        # 텍스트
    rich_payload  = models.JSONField(null=True, blank=True)        # 이미지/테이블 등 구조화
    updated_by    = models.BigIntegerField(null=True, blank=True)  # 마지막 수정자
    updated_at    = models.DateTimeField(auto_now=True)
    version       = models.IntegerField(default=1)                 # 낙관적 잠금

    class Meta:
        db_table = "meetings_block"
        indexes = [
            models.Index(fields=["meeting"]),
            models.Index(fields=["parent_block"]),
        ]

class BlockRevision(models.Model):
    block     = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="revisions")
    version   = models.IntegerField()
    snapshot  = models.JSONField()                                 # {type,level,text,rich_payload,order_no,...}
    edited_by = models.BigIntegerField(null=True, blank=True)
    edited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meetings_block_revision"
        indexes = [models.Index(fields=["block"])]

class Attachment(models.Model):
    meeting   = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="attachments")
    block     = models.ForeignKey(Block, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments")
    file_url  = models.TextField()                                 # presigned/정적 URL
    mime_type = models.CharField(max_length=200, null=True, blank=True)
    size      = models.BigIntegerField(null=True, blank=True)
    created_at= models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meetings_attachment"
        indexes = [models.Index(fields=["meeting"])]
