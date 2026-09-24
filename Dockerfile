FROM python:3.12.14-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

LABEL org.opencontainers.image.source="https://github.com/githuber110/ranzenpost"

ENV ISERV_DATA_DIR=/data ISERV_FRONTEND_DIR=/app/frontend PYTHONUNBUFFERED=1 TZ=Europe/Berlin

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock.txt
COPY backend/app /app/app
COPY frontend /app/frontend
COPY iserv_connector/run.sh /app/run.sh
RUN chmod a+x /app/run.sh

EXPOSE 8099
CMD ["/app/run.sh"]
