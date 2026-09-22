from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Analytics Service"
    API_V1_PREFIX: str = "/api/v1"

    # ── AWS / Athena ────────────────────────────────────────────────────────
    AWS_REGION: str = "us-east-1"
    ATHENA_OUTPUT_BUCKET: str          # s3://mi-bucket/athena-results/
    ATHENA_QUERY_TIMEOUT: int = 60     # segundos máximos esperando resultado

    # ── Glue Databases ──────────────────────────────────────────────────────
    # Nombres de las bases de datos en AWS Glue (creadas por los Crawlers).
    # Por convención, cada carpeta de S3 se convierte en una Glue DB distinta.
    GLUE_DB_CATALOGO: str = "astra_analytics"
    GLUE_DB_COMUNITY: str = "astra_analytics"
    GLUE_DB_ITERACTION: str = "astra_analytics"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
