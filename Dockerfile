FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir .

ENV PORT=10000

EXPOSE 10000

CMD ["python", "-m", "douyin_mcp_server.remote_server"]
