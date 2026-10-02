# UNVERIFIED IN THE BUILD SANDBOX (no network/Docker there).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 IMAGEAUDIT_HOME=/data/.imageaudit
WORKDIR /app
COPY pyproject.toml README.md ./
COPY imageaudit ./imageaudit
RUN pip install --no-cache-dir ".[api]" && useradd -m audit && mkdir -p /data && chown audit /data
USER audit
EXPOSE 8000
# Inside a container the API must bind 0.0.0.0; docker-compose publishes it on 127.0.0.1 only.
CMD ["imageaudit", "serve", "--host", "0.0.0.0", "--port", "8000"]
