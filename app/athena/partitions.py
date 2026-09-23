"""
Módulo de particiones: detecta la fecha más reciente disponible en el Data Lake
para evitar duplicados cuando se re-ejecuta la ingesta.

Reglas de particionado detectadas por el Crawler:
  - Tablas normales (movie, genre, artist, users, clubs...): partition_0 = fecha
  - Tabla iteraction (MongoDB): partition_0 = tipo ('reviews','likes',...), partition_1 = fecha
"""

import logging
from functools import lru_cache

from app.athena import run_query
from app.core.config import settings
from app.core.exceptions import AthenaQueryError, AthenaTimeoutError

log = logging.getLogger(__name__)

DB = settings.GLUE_DB_CATALOGO  # Todas las tablas están en la misma Glue DB


@lru_cache(maxsize=1)
def get_latest_partition() -> str:
    """
    Devuelve la fecha de partición más reciente encontrada en las tablas
    normales (ej. 'movie', 'users', 'clubs'). Usa la tabla 'movie' como
    referencia ya que siempre existe.

    El resultado se cachea en memoria durante el ciclo de vida del proceso
    (lru_cache), así solo se hace UNA query a Athena por arranque del servicio.

    Returns:
        str: fecha en formato 'YYYY-MM-DD', ej: '2026-09-17'
    """
    sql = f"""
        SELECT MAX(partition_0) AS latest_date
        FROM "{DB}"."movie"
    """
    try:
        rows = run_query(sql)
        if rows and rows[0].get("latest_date"):
            date = rows[0]["latest_date"]
            log.info(f"[Partitions] Fecha más reciente detectada: {date}")
            return date
    except (AthenaQueryError, AthenaTimeoutError) as e:
        log.warning(f"[Partitions] No se pudo detectar la partición: {e}")

    # Fallback: sin filtro de fecha (acepta todos los datos)
    return None


@lru_cache(maxsize=1)
def get_latest_iteraction_partition() -> str:
    """
    Devuelve la fecha de partición más reciente para la tabla 'iteraction'
    de MongoDB. En esta tabla el tipo está en partition_0 y la fecha en partition_1.

    Returns:
        str: fecha en formato 'YYYY-MM-DD', ej: '2026-09-17'
    """
    ITR = settings.GLUE_DB_ITERACTION
    sql = f"""
        SELECT MAX(partition_1) AS latest_date
        FROM "{ITR}"."iteraction"
    """
    try:
        rows = run_query(sql)
        if rows and rows[0].get("latest_date"):
            date = rows[0]["latest_date"]
            log.info(f"[Partitions] Fecha iteraction más reciente: {date}")
            return date
    except (AthenaQueryError, AthenaTimeoutError) as e:
        log.warning(f"[Partitions] No se pudo detectar partición de iteraction: {e}")

    return None


def partition_filter(table_alias: str = "", use_iteraction: bool = False) -> str:
    """
    Genera el fragmento WHERE/AND para filtrar por la partición más reciente.

    Args:
        table_alias: alias de la tabla en el SQL (ej: 'wr', 'm', 'c').
                     Si está vacío, no agrega prefijo de alias.
        use_iteraction: si True, usa partition_1 (fecha en tabla iteraction).
                        si False, usa partition_0 (fecha en tablas normales).

    Returns:
        str: fragmento SQL listo para insertar, ej:
             "AND wr.partition_0 = '2026-09-17'"
             o "" si no hay fecha disponible (acepta todos los datos)
    """
    if use_iteraction:
        date = get_latest_iteraction_partition()
        col = "partition_1"
    else:
        date = get_latest_partition()
        col = "partition_0"

    if not date:
        return ""  # sin filtro — fallback seguro

    prefix = f"{table_alias}." if table_alias else ""
    return f"AND {prefix}{col} = '{date}'"
