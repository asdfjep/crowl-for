#!/bin/bash
# deploy.sh - HS News Crawler + Analyzer 服务管理
# Usage: ./deploy.sh [--setup|--start|--stop|--restart|--status]

set -e

CRAWLER_DIR="/opt/hs-news-service"
ANALYZER_DIR="/opt/hs-news-analyzer"
ANALYZER_URL="${ANALYZER_URL:-http://localhost:8001/api/analyze}"
CRAWLER_INTERVAL="${CRAWLER_INTERVAL:-60}"

usage() {
    echo "Usage: $0 [--setup|--start|--stop|--restart|--status]"
    echo ""
    echo "  --setup    安装依赖，初始化环境"
    echo "  --start    启动所有服务"
    echo "  --stop     停止所有服务"
    echo "  --restart  重启所有服务"
    echo "  --status   查看服务状态"
    exit 1
}

setup() {
    echo "=== Installing dependencies ==="

    # Crawler service
    echo "--- hs-news-service ---"
    cd "$CRAWLER_DIR"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    playwright install --with-deps chromium 2>/dev/null || echo "Playwright install skipped"

    # Analyzer service
    echo "--- hs-news-analyzer ---"
    cd "$ANALYZER_DIR"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

    # Create data directories
    mkdir -p "$CRAWLER_DIR/data" "$ANALYZER_DIR/data" "$ANALYZER_DIR/reports"

    echo "Setup complete."
}

start() {
    echo "=== Starting services ==="

    # Start analyzer first (background, port 8001)
    cd "$ANALYZER_DIR"
    source venv/bin/activate
    nohup python server.py > /var/log/hs-news-analyzer.log 2>&1 &
    ANALYZER_PID=$!
    echo $ANALYZER_PID > /tmp/hs-news-analyzer.pid
    echo "Analyzer started (PID $ANALYZER_PID, port 8001)"

    # Wait for analyzer to be ready
    echo "Waiting for analyzer..."
    for i in $(seq 1 30); do
        if curl -s http://localhost:8001/api/health > /dev/null 2>&1; then
            echo "Analyzer ready."
            break
        fi
        sleep 1
    done

    # Start crawler (background, with push URL)
    cd "$CRAWLER_DIR"
    source venv/bin/activate
    export ANALYZER_URL="$ANALYZER_URL"
    nohup python run.py --interval "$CRAWLER_INTERVAL" > /var/log/hs-news-crawler.log 2>&1 &
    CRAWLER_PID=$!
    echo $CRAWLER_PID > /tmp/hs-news-crawler.pid
    echo "Crawler started (PID $CRAWLER_PID, interval ${CRAWLER_INTERVAL}min)"
}

stop() {
    echo "=== Stopping services ==="

    if [ -f /tmp/hs-news-crawler.pid ]; then
        PID=$(cat /tmp/hs-news-crawler.pid)
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "Crawler stopped (PID $PID)"
        else
            echo "Crawler PID $PID not running"
        fi
        rm -f /tmp/hs-news-crawler.pid
    else
        echo "Crawler: no PID file found"
    fi

    if [ -f /tmp/hs-news-analyzer.pid ]; then
        PID=$(cat /tmp/hs-news-analyzer.pid)
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "Analyzer stopped (PID $PID)"
        else
            echo "Analyzer PID $PID not running"
        fi
        rm -f /tmp/hs-news-analyzer.pid
    else
        echo "Analyzer: no PID file found"
    fi
}

status() {
    echo "=== Service Status ==="

    if [ -f /tmp/hs-news-crawler.pid ] && kill -0 $(cat /tmp/hs-news-crawler.pid) 2>/dev/null; then
        echo "  Crawler:  running (PID $(cat /tmp/hs-news-crawler.pid))"
    else
        echo "  Crawler:  stopped"
    fi

    if [ -f /tmp/hs-news-analyzer.pid ] && kill -0 $(cat /tmp/hs-news-analyzer.pid) 2>/dev/null; then
        echo "  Analyzer: running (PID $(cat /tmp/hs-news-analyzer.pid))"
        echo "  $(curl -s http://localhost:8001/api/health 2>/dev/null || echo 'health check failed')"
    else
        echo "  Analyzer: stopped"
    fi

    echo ""
    echo "  Logs:"
    echo "  Crawler:  /var/log/hs-news-crawler.log"
    echo "  Analyzer: /var/log/hs-news-analyzer.log"
}

case "${1:-}" in
    --setup)   setup ;;
    --start)   start ;;
    --stop)    stop ;;
    --restart) stop; sleep 2; start ;;
    --status)  status ;;
    *)         usage ;;
esac
