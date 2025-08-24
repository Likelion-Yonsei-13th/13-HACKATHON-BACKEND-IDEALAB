# analytics/management/commands/backfill_closure_signgu_codes.py
from django.core.management.base import BaseCommand
from analytics.models import ClosureStat
try:
    from analytics.services.region import name_to_signgu_cd
except Exception:
    def name_to_signgu_cd(x): return None  # 안전장치

class Command(BaseCommand):
    help = "ClosureStat의 signgu_cd가 비어있는 행을 자치구 이름(signgu_cd_nm)으로 보정합니다."

    def handle(self, *args, **opts):
        updated = 0
        skipped = 0
        qs = ClosureStat.objects.filter(signgu_cd__isnull=True)
        for row in qs.iterator():
            code = name_to_signgu_cd(row.signgu_cd_nm)
            if code:
                row.signgu_cd = code
                row.save(update_fields=["signgu_cd"])
                updated += 1
            else:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(f"Backfilled signgu_cd: updated={updated}, skipped={skipped}"))
