# analytics/management/commands/sync_trading_areas.py
from django.core.management.base import BaseCommand
from django.db import transaction
from analytics.models import TradingArea
from analytics.services.seoul_openapi import iter_TbgisTrdarRelm

class Command(BaseCommand):
    help = "서울시 상권영역(TbgisTrdarRelm) 동기화"

    def handle(self, *args, **options):
        self.stdout.write("Fetching TbgisTrdarRelm...")

        field_names = {f.name for f in TradingArea._meta.get_fields()}

        # ✅ 모델 실제 필드명에 맞춘 매핑
        mapping_candidates = {
            # pk는 trdar_cd (update_or_create에서 별도 지정)
            "trdar_se_cd": ("TRDAR_SE_CD",),
            "trdar_se_cd_nm": ("TRDAR_SE_CD_NM",),
            "trdar_cd_nm": ("TRDAR_CD_NM",),

            # 좌표 (TM중부 X/Y)
            "x": ("XCNTS_VALUE",),
            "y": ("YDNTS_VALUE",),

            # 자치구
            "signgu_cd": ("SIGNGU_CD",),
            "signgu_cd_nm": ("SIGNGU_CD_NM",),

            # 행정동
            "adstrd_cd": ("ADSTRD_CD",),
            "adstrd_cd_nm": ("ADSTRD_CD_NM",),

            # 면적
            "area_m2": ("RELM_AR",),
        }

        inserted = 0
        updated = 0

        def cast_number_if_needed(field, val):
            if val in (None, ""):
                return None
            # 좌표/면적은 숫자
            if field in {"x", "y", "area_m2"}:
                try:
                    return float(val)
                except Exception:
                    return None
            return val

        with transaction.atomic():
            for r in iter_TbgisTrdarRelm():
                trdar_cd = r.get("TRDAR_CD")
                if not trdar_cd:
                    continue

                defaults = {}
                for model_field, api_keys in mapping_candidates.items():
                    if model_field not in field_names:
                        continue
                    for k in api_keys:
                        if k in r and r[k] not in (None, ""):
                            val = cast_number_if_needed(model_field, r[k])
                            if val is not None:
                                defaults[model_field] = val
                            break

                obj, created = TradingArea.objects.update_or_create(
                    trdar_cd=trdar_cd, defaults=defaults
                )
                inserted += int(created)
                updated += int(not created)

        self.stdout.write(f"Inserted ~{inserted} rows (existing ignored).")
        self.stdout.write("Reconciling deltas (name/coords/area)...")
        self.stdout.write(f"Updated {updated} existing rows.")
