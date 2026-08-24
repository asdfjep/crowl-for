FROM python:3.12-slim

# Use Alibaba Cloud mirrors for faster downloads in China
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

# Install system dependencies
ENV TZ=Asia/Shanghai
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    chromium \
    chromium-driver \
    tzdata \
    && ln -fs /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright (Python only, skip browser download)
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --no-cache-dir playwright && \
    playwright install-deps chromium

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Create data dir
RUN mkdir -p /app/data

# Set playwright to use system chromium
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers

# Expose port for FastAPI
EXPOSE 8000

# Run the service
CMD ["python", "run.py", "--admin", "--port", "8000", "--host", "0.0.0.0"]
