from django.core.management.base import BaseCommand
from analytics.models import ChangeIndex

class Command(BaseCommand):
    help = "raw_data에 있는 상권변화지표 레이블(change_level)만 백필 (숫자 필드 안 건드림)"

    def handle(self, *args, **opts):
        qs = ChangeIndex.objects.all()
        updated = 0
        for obj in qs.iterator(chunk_size=2000):
            raw = obj.raw_data or {}
            snake = raw.get("snake", {})
            original = raw.get("original", {})

            # 표기(한글) 레벨만 안전하게 채움
            name = snake.get("상권_변화_지표_명") or original.get("상권_변화_지표_명")

            if name and (getattr(obj, "change_level", None) in (None, "")):
                obj.change_level = name
                obj.save(update_fields=["change_level"])
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"ChangeIndex backfilled (level only): updated={updated}"))
