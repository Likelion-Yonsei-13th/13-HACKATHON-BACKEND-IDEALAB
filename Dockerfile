FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    pkg-config \
    default-libmysqlclient-dev \
    # ↓ PyAudio를 requirements에 넣었다면 이 두 줄도 필요
    portaudio19-dev libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install -r requirements.txt

#첫번째 점: 내 컴퓨터의 현재 폴더의 모든 것, 두번째 점: 컨테이너의 현재 작업 디렉토리
COPY . . 

#추후 수정 예정
CMD ["gunicorn", "IDEALAB.wsgi:application", "--bind", "0.0.0.0:8000", "--chdir", "/app/IDEALAB"]
