FROM python:3.12-slim

ENV ISERV_DATA_DIR=/data ISERV_FRONTEND_DIR=/app/frontend PYTHONUNBUFFERED=1 TZ=Europe/Berlin

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY backend/app /app/app
COPY frontend /app/frontend
COPY iserv_connector/run.sh /app/run.sh
RUN chmod a+x /app/run.sh

EXPOSE 8099
CMD ["/app/run.sh"]
