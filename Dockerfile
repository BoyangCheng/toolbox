# syntax=docker/dockerfile:1.6
FROM python:3.12-slim

# System packages: tini for proper PID 1 signal handling
RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY toolbox/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY toolbox/ ./

# Entrypoint that wires persistent storage into /app via symlinks
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV SERVER_MODE=prod \
    PORT=5000 \
    PYTHONUNBUFFERED=1 \
    PERSIST_DIR=/persist \
    TZ=Asia/Shanghai

EXPOSE 5000

# Healthcheck: hit the login page; HTTP 200 means waitress is serving
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:5000/login',timeout=3); sys.exit(0)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "app.py"]
