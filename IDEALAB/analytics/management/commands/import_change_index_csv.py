from django.core.management.base import BaseCommand
from analytics.models import ChangeIndex
from analytics.services.csv_loader import read_csv_rows
import re

def to_snake(s: str) -> str:
    s = re.sub(r"[^\w]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_").lower()

def to_float_or_none(v):
    if v is None:
        return None
    t = str(v).strip().replace(",", "")
    if t == "" or t.upper() == "NULL":
        return None
    try:
        return float(t)
    except Exception:
        return None

class Command(BaseCommand):
    help = "CSV에서 상권변화지표 전 컬럼을 ChangeIndex.raw_data에 저장 + 핵심 필드 저장"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="CSV 파일 경로")
        parser.add_argument("--encoding", type=str, default="cp949")
        # 컬럼명 지정 (없으면 자동 탐색)
        parser.add_argument("--yyq_col", type=str, help="기준_년분기_코드 / STDR_YYQU_CD")
        parser.add_argument("--trdar_col", type=str, help="상권_코드 / TRDAR_CD")
        parser.add_argument("--idx_col", type=str, help="상권_변화_지표 / CHG_IDX")
        parser.add_argument("--lvl_col", type=str, help="상권_변화_지표_등급 등")

    def handle(self, *args, **opts):
        path = opts["csv_path"]
        encoding = opts["encoding"]
        yyq_col = opts.get("yyq_col")
        trdar_col = opts.get("trdar_col")
        idx_col = opts.get("idx_col")
        lvl_col = opts.get("lvl_col")

        created = updated = 0

        for r in read_csv_rows(path, encoding=encoding):
            # 키 탐색
            yyq = r.get(yyq_col or "기준_년분기_코드") or r.get("STDR_YYQU_CD")
            trdar = r.get(trdar_col or "상권_코드") or r.get("TRDAR_CD")
            if not yyq or not trdar:
                self.stdout.write(self.style.WARNING(f"Skip row (missing keys): {r}"))
                continue

            # 지표/등급 탐색
            idx_val = r.get(idx_col or "상권_변화_지표") or r.get("CHG_IDX")
            lvl_val = r.get(lvl_col or "상권_변화_지표_등급") or r.get("CHG_LVL")

            std = {
                "yyq": str(yyq).strip(),
                "trdar_cd": str(trdar).strip(),
                "change_index": to_float_or_none(idx_val),
                "change_level": str(lvl_val).strip() if lvl_val else None,
            }

            # raw_data 저장: 원본 + snake
            raw_store = {"original": dict(r), "snake": {}}
            for k, v in r.items():
                raw_store["snake"][to_snake(k)] = v

            obj, is_created = ChangeIndex.objects.update_or_create(
                yyq=std["yyq"],
                trdar_cd=std["trdar_cd"],
                defaults={**std, "raw_data": raw_store},
            )
            created += int(is_created)
            updated += int(not is_created)

        self.stdout.write(self.style.SUCCESS(
            f"[ChangeIndex] upserted: created={created}, updated={updated}"
        ))
