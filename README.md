# 13-HACKATHON-BACKEND-IDEALAB

# IDEALAB Backend

Django + DRF 기반 상권/지표/미팅 백엔드.  
런타임은 Docker + Gunicorn, 앞단은 Nginx 리버스 프록시. DB는 AWS RDS(MySQL).

---

## ⚙️ Tech Stack

- Python 3.11, Django 5.x, DRF  
- MySQL (RDS)  
- Gunicorn, Nginx, Docker / docker-compose  
- (데이터 적재) 커스텀 Django management commands  
- (외부) 서울 열린데이터 API  

---

## 📂 프로젝트 구조

```
IDEALAB/
├─ IDEALAB/                 # settings, urls
├─ analytics/               # 상권/지표/통계
│  ├─ models.py             # TradingArea, IndustryMetric, ChangeIndex, ClosureStat, StoreCount ...
│  ├─ views.py              # /api/analytics/*
│  ├─ urls.py
│  ├─ services/
│  │  ├─ csv_loader.py      # CSV 로더 유틸
│  │  ├─ region.py          # 자치구 이름↔코드 매핑 등
│  │  ├─ seoul_openapi.py   # 서울 열린API 호출
│  │  └─ store_radius.py    # 반경 상가 조회/집계 클라이언트
│  └─ management/commands/  # 데이터 적재/동기화 명령
├─ user/                    # 회원 기능
│  ├─ views.py              # signup/login/logout
│  └─ urls.py               # api/user/
├─ meetings/                # 회의/블록 등
└─ ...
```

---

## 🔑 환경 변수

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`  
- `DJANGO_SECRET_KEY`  
- `DJANGO_DEBUG` (`True`/`False`)  
- `ALLOWED_HOSTS` (쉼표 구분: `43.204.22.115,api.example.com`)  
- `CORS_ALLOWED_ORIGINS` (예: `https://idealab-yonsei.netlify.app,https://gleeful-duckanoo.netlify.app`)  
- `SEOUL_OPEN_API_KEY` (또는 `SEOUL_STORE_API_KEY`)  
- `SEOUL_OPENAPI_BASE` (기본값: `http://openapi.seoul.go.kr:8088`)  

⚠️ `CORS_ALLOWED_ORIGINS`는 반드시 **경로 없는 Origin만** 허용해야 합니다.  
예: ✅ `https://site.netlify.app` / ❌ `https://site.netlify.app/abc`

---

## 🖥️ 로컬 개발

```bash
# 가상환경 & 의존성 설치
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 환경 변수
cp .env.example .env  # 값 채우기

# 마이그레이션
python manage.py migrate

# 개발 서버 실행
python manage.py runserver
```

---

## 🐳 Docker / Compose

### 빌드 & 실행

```bash
docker compose build
docker compose up -d
```

- 웹 컨테이너: `web` (Gunicorn: `:8000`)  
- Nginx 컨테이너: `nginx` (`:80` → `web:8000`)  
- 정적파일: `collectstatic` 후 `/static/` alias  
- 데이터 공유: `./data:/app/data` 볼륨 권장  

---

## 🌐 URL 라우팅

- `admin/`  
- `api/`  
- `api/user/`  
  - `signup/` (POST)  
  - `login/` (POST)  
  - `logout/` (POST)  

⚠️ **APPEND_SLASH=True** → POST 요청 시 **슬래시 포함 필요**  
예: `/api/user/login/` ✅ / `/api/user/login` ❌

---

## 📊 데이터 적재 (Management Commands)

### 상권 마스터
```bash
python manage.py import_trading_areas_csv data/trading_area.csv --encoding cp949
```

### 업종/상권 분기 매출
```bash
python manage.py import_industry_metrics_csv data/sales_2024.csv \\
  --yyq_col "기준_년분기_코드" \\
  --trdar_col "상권_코드" \\
  --svc_cd_col "서비스_업종_코드" \\
  --svc_nm_col "서비스_업종_코드_명" \\
  --amt_col "당월_매출_금액" \\
  --cnt_col "당월_매출_건수" \\
  --encoding cp949
```

### 상권 변화 지표
```bash
python manage.py import_change_index_csv data/change_index_2024.csv \\
  --encoding cp949 \\
  --yyq_col "기준_년분기_코드" \\
  --trdar_col "상권_코드" \\
  --idx_col "상권_변화_지표" \\
  --lvl_col "상권_변화_지표_등급"
```

### 폐업 통계
```bash
python manage.py import_closures_csv data/closures_2023.csv \\
  --encoding cp949 \\
  --wide_year 2023 \\
  --melt_cols "전체,외식업,서비스업,소매업" \\
  --signgu_nm_col "자치구별(1)" \\
  --skip_total_row
```

자치구 코드 보정:
```bash
python manage.py backfill_closure_signgu_codes
```

---

## 🛰️ 서울 열린데이터 API 연동

### 상권 메타 동기화
```bash
python manage.py sync_trading_areas
```

### 반경 내 상가업소 집계
```bash
python manage.py fetch_store_counts --radius 2000 --api-key "$SEOUL_OPEN_API_KEY"
```

---

## 🚀 배포 플로우

```bash
# 마이그레이션
python manage.py migrate

# 정적 파일
python manage.py collectstatic --noinput

# docker-compose로 실행
docker compose up -d
```

---

## 🛠️ 트러블슈팅

- **400 DisallowedHost** → `ALLOWED_HOSTS`에 IP/도메인 추가  
- **CORS 에러 (E014)** → `CORS_ALLOWED_ORIGINS` 값 확인  
- **CSV 깨짐** → `--encoding cp949` 또는 `utf-8-sig` 지정  
- **컨테이너 경로 문제** → 항상 `/app/data/...` 기준  
- **No space left on device** → `docker system prune -af` / 데이터는 볼륨 사용  
- **서울 열린API ERROR-331** → JSON 포맷 불안정 → CSV 사용 권장  
- **Connection reset by peer** → 공공 API 일시 오류 → 재시도 필요  
- **signgu_cd 백필 실패** → `region.py` 매핑 테이블에 이름 누락 확인 (`서울시` 등 추가 필요)  

---