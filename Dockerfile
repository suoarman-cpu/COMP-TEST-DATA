# Render 말고 다른 곳(Cloud Run, Fly.io 등)에 올릴 때 쓴다.
FROM python:3.12-slim

WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY turbochiller/ ./turbochiller/

# 호스팅 업체가 PORT 를 정해 준다
ENV PORT=8000
EXPOSE 8000

# TURBOCHILLER_PASSWORD 는 이미지에 넣지 않는다.
# 실행할 때 환경변수로 준다.
CMD exec gunicorn turbochiller.wsgi:application \
    --bind 0.0.0.0:$PORT --workers 2 --timeout 120
