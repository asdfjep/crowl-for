# Single-stage build: the Vue frontend is built on the dev machine
# (`cd frontend && npm run build`, output -> static/) and committed to git,
# so the server only ever needs ONE base image and no Node toolchain.
FROM python:3.12-slim

# Use a China PyPI mirror when the server cannot reach pypi.org:
#   PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple docker compose up -d --build
ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/reports

ENV NEWS_DATA_DIR=/app/data
ENV NEWS_REPORT_DIR=/app/reports
ENV NEWS_GENERATE_HTML_BRIEF=1

EXPOSE 8011

CMD ["python", "server.py"]