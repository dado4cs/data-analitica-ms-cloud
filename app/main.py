import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.router import api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Microservicio de analítica para ProyCloud. "
        "Realiza consultas SQL cruzadas sobre AWS Athena (catálogo + comunidad) "
        "y expone los resultados como endpoints REST para el frontend."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — ajusta origins según tu despliegue
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": settings.APP_NAME}


app.include_router(api_router, prefix=settings.API_V1_PREFIX)
