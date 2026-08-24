# Single-stage build: the Vue frontend is built on the dev machine
# (`cd frontend && npm run build`, output -> static/) and committed to git,
# so the server only ever needs ONE base image and no Node toolchain.
#
# The base image is referenced by its full daocloud mirror domain so the
# server does not need any registry-mirror config in /etc/docker/daemon.json.
FROM docker.m.daocloud.io/library/python:3.12-slim

# China PyPI mirror is the default so pip install does not depend on pypi.org.
# Override with: docker compose build --build-arg PIP_INDEX_URL=<index>
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

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