# ---- Stage 1: build the Vue frontend ----
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime serving API + static frontend ----
FROM python:3.12-slim
WORKDIR /app

# Chinese fonts so PDF/report rendering never regresses in the container
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Serve the built SPA as the static root of the FastAPI app
COPY --from=frontend /app/frontend/dist ./static

RUN mkdir -p /app/data /app/reports

ENV NEWS_DATA_DIR=/app/data
ENV NEWS_REPORT_DIR=/app/reports
ENV NEWS_GENERATE_HTML_BRIEF=1

EXPOSE 8011

CMD ["python", "server.py"]