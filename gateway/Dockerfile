FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN useradd --system --uid 10001 --no-create-home gateway
USER 10001

EXPOSE 8443
CMD ["uvicorn", "--factory", "app.main:create_app", \
     "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/certs/server.key", "--ssl-certfile", "/certs/server.pem"]
