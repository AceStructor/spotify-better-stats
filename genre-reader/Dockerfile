FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY genre-reader/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY genre-reader .
COPY listener .

CMD ["python", "listener.py"]
