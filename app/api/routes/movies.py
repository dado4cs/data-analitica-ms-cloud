"""
Endpoints de analítica de películas.

Todas las queries cruzan la Glue DB 'catalogo' con 'comunity'
para obtener insights reales de negocio.
"""

from fastapi import APIRouter, HTTPException, Query

from app.athena import run_query
from app.core.config import settings
from app.core.exceptions import AthenaQueryError, AthenaTimeoutError

router = APIRouter(prefix="/movies", tags=["Movies Analytics"])

CAT = settings.GLUE_DB_CATALOGO
COM = settings.GLUE_DB_COMUNITY


@router.get("/top-watched")
def top_watched_movies(limit: int = Query(default=10, ge=1, le=100)):
    """
    Las películas más vistas en salas de reproducción grupal.
    Cruza: comunity.watch_rooms  ↔  catalogo.movie
    """
    sql = f"""
        SELECT
            m.title,
            m.release_year,
            m.rating,
            COUNT(wr.id) AS total_salas
        FROM "{COM}"."watch_rooms" wr
        JOIN "{CAT}"."movie" m
          ON wr.movie_id = m.public_id
        GROUP BY m.title, m.release_year, m.rating
        ORDER BY total_salas DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/by-actor")
def movies_by_actor(
    actor: str = Query(..., description="Nombre del actor o director"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Películas en las que aparece un actor/director y cuántas salas las han reproducido.
    Cruza: catalogo.artist ↔ catalogo.movie_artist ↔ catalogo.movie ↔ comunity.watch_rooms
    """
    sql = f"""
        SELECT
            m.title,
            m.release_year,
            a.name  AS artist_name,
            a.type  AS artist_type,
            COUNT(wr.id) AS total_salas
        FROM "{CAT}"."artist" a
        JOIN "{CAT}"."movie_artist" ma ON a.id = ma.artist_id
        JOIN "{CAT}"."movie"        m  ON ma.movie_id = m.id
        LEFT JOIN "{COM}"."watch_rooms" wr ON wr.movie_id = m.public_id
        WHERE LOWER(a.name) LIKE LOWER('%{actor}%')
        GROUP BY m.title, m.release_year, a.name, a.type
        ORDER BY total_salas DESC, m.title
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/by-genre")
def movies_by_genre(
    genre: str = Query(..., description="Nombre del género (ej: Action, Drama)"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Películas de un género y sus estadísticas de visualización.
    Cruza: catalogo.genre ↔ catalogo.movie_genre ↔ catalogo.movie ↔ comunity.watch_rooms
    """
    sql = f"""
        SELECT
            m.title,
            m.release_year,
            m.rating,
            g.name  AS genre,
            COUNT(wr.id) AS total_salas
        FROM "{CAT}"."genre" g
        JOIN "{CAT}"."movie_genre" mg ON g.id = mg.genre_id
        JOIN "{CAT}"."movie"       m  ON mg.movie_id = m.id
        LEFT JOIN "{COM}"."watch_rooms" wr ON wr.movie_id = m.public_id
        WHERE LOWER(g.name) LIKE LOWER('%{genre}%')
        GROUP BY m.title, m.release_year, m.rating, g.name
        ORDER BY total_salas DESC, m.rating DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/top-by-genre")
def top_movies_per_genre(limit_per_genre: int = Query(default=5, ge=1, le=20)):
    """
    Las N películas más vistas por cada género.
    Cruza: catalogo.genre ↔ catalogo.movie_genre ↔ catalogo.movie ↔ comunity.watch_rooms
    """
    sql = f"""
        WITH ranked AS (
            SELECT
                g.name  AS genre,
                m.title,
                m.rating,
                COUNT(wr.id) AS total_salas,
                ROW_NUMBER() OVER (
                    PARTITION BY g.name
                    ORDER BY COUNT(wr.id) DESC
                ) AS rn
            FROM "{CAT}"."genre" g
            JOIN "{CAT}"."movie_genre" mg ON g.id = mg.genre_id
            JOIN "{CAT}"."movie"       m  ON mg.movie_id = m.id
            LEFT JOIN "{COM}"."watch_rooms" wr ON wr.movie_id = m.public_id
            GROUP BY g.name, m.title, m.rating
        )
        SELECT genre, title, rating, total_salas
        FROM ranked
        WHERE rn <= {limit_per_genre}
        ORDER BY genre, total_salas DESC
    """
    return _execute(sql)


def _execute(sql: str):
    try:
        return run_query(sql)
    except AthenaQueryError as e:
        raise HTTPException(status_code=500, detail=f"Error en Athena: {e}")
    except AthenaTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Timeout en Athena: {e}")
