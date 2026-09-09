FROM python:3.12-slim

LABEL maintainer="villabos"
LABEL description="Analytics Service — FastAPI + AWS Athena"

ENV APP_NAME="Analytics Service" \
    API_V1_PREFIX="/api/v1" \
    AWS_REGION="us-east-1" \
    ATHENA_QUERY_TIMEOUT=60 \
    GLUE_DB_CATALOGO="catalogo" \
    GLUE_DB_COMUNITY="comunity" \
    GLUE_DB_FRONTEND="frontend"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
