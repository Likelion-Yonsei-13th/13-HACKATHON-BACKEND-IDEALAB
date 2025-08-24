from django.core.management.base import BaseCommand
from django.db import transaction
from analytics.models import TradingArea
from analytics.services.seoul_openapi import iter_TbgisTrdarRelm

class Command(BaseCommand):
    help = "TbgisTrdarRelm 응답을 이용해 TradingArea의 자치구/행정동 컬럼을 백필(update)합니다."

    def handle(self, *args, **opts):
        updated = 0
        missing = 0
        seen = 0

        with transaction.atomic():
            for row in iter_TbgisTrdarRelm():
                seen += 1
                trdar = row.get("TRDAR_CD")
                if not trdar:
                    continue

                try:
                    ta = TradingArea.objects.get(trdar_cd=trdar)
                except TradingArea.DoesNotExist:
                    missing += 1
                    continue

                # 응답 필드 → 모델 필드 매핑
                new_sigungu_cd   = row.get("SIGNGU_CD") or ""
                new_sigungu_nm   = row.get("SIGNGU_CD_NM") or ""
                new_adstrd_cd    = row.get("ADSTRD_CD") or ""
                new_adstrd_nm    = row.get("ADSTRD_CD_NM") or ""

                dirty = False
                if new_sigungu_cd and ta.sigungu_cd != new_sigungu_cd:
                    ta.sigungu_cd = new_sigungu_cd
                    dirty = True
                if new_sigungu_nm and ta.sigungu_cd_nm != new_sigungu_nm:
                    ta.sigungu_cd_nm = new_sigungu_nm
                    dirty = True
                if new_adstrd_cd and ta.adstrd_cd != new_adstrd_cd:
                    ta.adstrd_cd = new_adstrd_cd
                    dirty = True
                if new_adstrd_nm and ta.adstrd_cd_nm != new_adstrd_nm:
                    ta.adstrd_cd_nm = new_adstrd_nm
                    dirty = True

                if dirty:
                    ta.save(update_fields=["sigungu_cd","sigungu_cd_nm","adstrd_cd","adstrd_cd_nm"])
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed={seen}, Updated={updated}, Missing TRDAR in DB={missing}"
        ))
