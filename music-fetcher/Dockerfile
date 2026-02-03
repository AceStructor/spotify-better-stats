FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y gcc libpq-dev ffmpeg && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL https://deno.land/install.sh | sh && \
    ln -s /root/.deno/bin/deno /usr/local/bin/deno

COPY music-fetcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY music-fetcher/*.py .
COPY music-fetcher/beets/beets_config.yaml /import/beets/

CMD ["python", "fetcher.py"]
