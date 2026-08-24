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

COPY requirements.txt requirements-crawler.txt ./
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt -r requirements-crawler.txt

# --- Playwright Chromium (for browser-rendered sources) --------------------
# Chromium system libs come from apt; rewrite the Debian mirror to TUNA so the
# install works from CN networks. The browser binary is downloaded from the
# npmmirror CDN instead of the default Microsoft CDN (likewise often blocked).
RUN sed -i 's@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g' \
      /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list 2>/dev/null || true \
 && apt-get update \
 && python -m playwright install-deps chromium \
 && rm -rf /var/lib/apt/lists/*

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
RUN python -m playwright install chromium
# ---------------------------------------------------------------------------

COPY . .

# Crawler service: the analyzer's run.py expects one under
#   ~/.openclaw/workspace/.tmp_<topic>_news_service/<topic>-news-service
# All topic paths symlink to the single vendored crawler
# (crawler/hs-news-service); per-topic filtering happens inside the analyzer.
RUN mkdir -p \
      /root/.openclaw/workspace/.tmp_ai_news_service \
      /root/.openclaw/workspace/.tmp_commercial_space_news_service \
      /root/.openclaw/workspace/.tmp_display_polarizer_news_service \
 && ln -sf /app/crawler/hs-news-service /root/.openclaw/workspace/.tmp_ai_news_service/ai-news-service \
 && ln -sf /app/crawler/hs-news-service /root/.openclaw/workspace/.tmp_commercial_space_news_service/commercial-space-news-service \
 && ln -sf /app/crawler/hs-news-service /root/.openclaw/workspace/.tmp_display_polarizer_news_service/display-polarizer-news-service

RUN mkdir -p /app/data /app/reports

ENV NEWS_DATA_DIR=/app/data
ENV NEWS_REPORT_DIR=/app/reports
ENV NEWS_GENERATE_HTML_BRIEF=1

EXPOSE 8011

CMD ["python", "server.py"]