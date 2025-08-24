# analytics/management/commands/import_industry_metrics_csv.py
from django.core.management.base import BaseCommand
from analytics.models import IndustryMetric
from analytics.services.csv_loader import read_csv_rows, to_decimal_safe

class Command(BaseCommand):
    help = "업종/상권 분기 매출 CSV 적재 (VwsmTrdarSelngQq 다운본 등)"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument("--yyq_col", type=str, default="STDR_YYQU_CD")   # 예: 2023Q4
        parser.add_argument("--trdar_col", type=str, default="TRDAR_CD")
        parser.add_argument("--svc_cd_col", type=str, default="SVC_INDUTY_CD")
        parser.add_argument("--svc_nm_col", type=str, default="SVC_INDUTY_CD_NM")
        parser.add_argument("--amt_col", type=str, default="THSMON_SELNG_AMT")
        parser.add_argument("--cnt_col", type=str, default="THSMON_SELNG_CO")

    def handle(self, *args, **opts):
        path = opts["csv_path"]
        yyq_col = opts["yyq_col"]
        trdar_col = opts["trdar_col"]
        svc_cd_col = opts["svc_cd_col"]
        svc_nm_col = opts["svc_nm_col"]
        amt_col = opts["amt_col"]
        cnt_col = opts["cnt_col"]

        created = updated = 0
        for r in read_csv_rows(path):
            trdar = (r.get(trdar_col) or "").strip()
            yyq = (r.get(yyq_col) or "").strip()
            if not trdar or not yyq:
                continue

            defaults = {
                "svc_induty_cd": r.get(svc_cd_col) or None,
                "svc_induty_cd_nm": r.get(svc_nm_col) or None,
                "thsmon_selng_amt": to_decimal_safe(r.get(amt_col)),
                "thsmon_selng_co": to_decimal_safe(r.get(cnt_col)),
                "mdwk_selng_amt": to_decimal_safe(r.get("MDWK_SELNG_AMT")),
                "wkend_selng_amt": to_decimal_safe(r.get("WKEND_SELNG_AMT")),
            }
            obj, is_created = IndustryMetric.objects.update_or_create(
                trdar_cd=trdar, yyq=yyq, svc_induty_cd=defaults["svc_induty_cd"], defaults=defaults
            )
            created += int(is_created)
            updated += int(not is_created)

        self.stdout.write(self.style.SUCCESS(f"[IndustryMetric] upserted: created={created}, updated={updated}"))
