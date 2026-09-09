"""
Cliente de AWS Athena.

Athena funciona de forma asíncrona:
  1. submit_query()  → devuelve un execution_id
  2. poll()          → espera hasta que el estado sea SUCCEEDED, FAILED o CANCELLED
  3. fetch_results() → convierte la respuesta en una lista de dicts

Este módulo encapsula ese ciclo completo en una sola función: run_query()
"""

import time
import logging

import boto3

from app.core.config import settings
from app.core.exceptions import AthenaQueryError, AthenaTimeoutError

log = logging.getLogger(__name__)


def _get_client():
    return boto3.client("athena", region_name=settings.AWS_REGION)


def run_query(sql: str) -> list[dict]:
    """
    Ejecuta una consulta SQL en Athena y devuelve los resultados como
    una lista de diccionarios {columna: valor}.

    Args:
        sql: Consulta SQL válida para Athena (puede hacer JOIN entre
             distintas Glue databases, ej: catalogo.movie y comunity.watch_rooms).

    Returns:
        Lista de filas como dicts.

    Raises:
        AthenaQueryError: Si Athena reporta FAILED o CANCELLED.
        AthenaTimeoutError: Si la query no termina antes de ATHENA_QUERY_TIMEOUT.
    """
    client = _get_client()

    log.info(f"[Athena] Ejecutando query:\n{sql}")

    # 1. Enviar la query
    response = client.start_query_execution(
        QueryString=sql,
        ResultConfiguration={
            "OutputLocation": settings.ATHENA_OUTPUT_BUCKET,
        },
    )
    execution_id = response["QueryExecutionId"]
    log.info(f"[Athena] QueryExecutionId: {execution_id}")

    # 2. Esperar resultado (polling)
    deadline = time.time() + settings.ATHENA_QUERY_TIMEOUT
    delay    = 1.0  # segundos entre intentos

    while time.time() < deadline:
        state_response = client.get_query_execution(QueryExecutionId=execution_id)
        state = state_response["QueryExecution"]["Status"]["State"]

        if state == "SUCCEEDED":
            break
        elif state in ("FAILED", "CANCELLED"):
            reason = state_response["QueryExecution"]["Status"].get(
                "StateChangeReason", "Sin detalle"
            )
            raise AthenaQueryError(f"Athena {state}: {reason}")

        log.debug(f"[Athena] Estado: {state}. Reintentando en {delay}s...")
        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)  # back-off exponencial, máx 5s
    else:
        raise AthenaTimeoutError(
            f"La query no terminó en {settings.ATHENA_QUERY_TIMEOUT}s (id={execution_id})"
        )

    # 3. Obtener resultados
    paginator = client.get_paginator("get_query_results")
    pages = paginator.paginate(QueryExecutionId=execution_id)

    rows   = []
    header = None

    for page in pages:
        result_rows = page["ResultSet"]["Rows"]
        if header is None:
            # La primera fila de la primera página son los encabezados
            header = [col["VarCharValue"] for col in result_rows[0]["Data"]]
            result_rows = result_rows[1:]

        for row in result_rows:
            values = [cell.get("VarCharValue", None) for cell in row["Data"]]
            rows.append(dict(zip(header, values)))

    log.info(f"[Athena] Resultado: {len(rows)} filas.")
    return rows
