# analytics/management/commands/import_trading_areas_csv.py
from django.core.management.base import BaseCommand
from analytics.models import TradingArea
from analytics.services.csv_loader import read_csv_rows

class Command(BaseCommand):
    help = "CSV로 상권(소권역) 마스터 적재"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **opts):
        path = opts["csv_path"]
        created = updated = 0
        for r in read_csv_rows(path):
            trdar_cd = (r.get("TRDAR_CD") or r.get("trdar_cd") or "").strip()
            if not trdar_cd:
                continue

            defaults = {
                "trdar_cd_nm": r.get("TRDAR_CD_NM") or r.get("name"),
                "trdar_se_cd": r.get("TRDAR_SE_CD"),
                "trdar_se_cd_nm": r.get("TRDAR_SE_CD_NM"),
                "x": float(r["XCNTS_VALUE"]) if r.get("XCNTS_VALUE") else None,
                "y": float(r["YDNTS_VALUE"]) if r.get("YDNTS_VALUE") else None,
                "signgu_cd": r.get("SIGNGU_CD"),
                "signgu_cd_nm": r.get("SIGNGU_CD_NM"),
                "adstrd_cd": r.get("ADSTRD_CD"),
                "adstrd_cd_nm": r.get("ADSTRD_CD_NM"),
                "area_m2": float(r["RELM_AR"]) if r.get("RELM_AR") else None,
            }
            obj, is_created = TradingArea.objects.update_or_create(
                trdar_cd=trdar_cd, defaults=defaults
            )
            created += int(is_created)
            updated += int(not is_created)
        self.stdout.write(self.style.SUCCESS(f"TradingArea upserted: created={created}, updated={updated}"))
