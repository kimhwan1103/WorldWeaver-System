# ── Stage 1: 프론트엔드 빌드 ──
FROM node:22-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./

# 프로덕션에서는 같은 서버에서 서빙하므로 API_BASE를 빈 문자열로 설정
ENV VITE_API_BASE=""
RUN npm run build


# ── Stage 2: Python 백엔드 ──
FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# 소스 코드
COPY worldweaver/ worldweaver/
COPY prompts/ prompts/
COPY lore_documents/ lore_documents/
COPY main.py run_server.py ./

# 프론트엔드 빌드 결과물 복사
COPY --from=frontend-build /app/frontend/dist frontend/dist/

# 로그/업로드 디렉토리
RUN mkdir -p logs uploads

# 환경변수 기본값
ENV DEMO_MODE=true
ENV DAILY_LLM_LIMIT=500
ENV CORS_ORIGINS="*"
ENV PORT=8000

EXPOSE ${PORT}

CMD python -m uvicorn worldweaver.api.server:app --host 0.0.0.0 --port ${PORT:-8000}
