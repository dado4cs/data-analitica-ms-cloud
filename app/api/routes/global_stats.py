"""
Endpoints de analítica de clubes y géneros (vista global del sistema).
"""

from fastapi import APIRouter, HTTPException, Query

from app.athena import run_query
from app.core.config import settings
from app.core.exceptions import AthenaQueryError, AthenaTimeoutError

router = APIRouter(tags=["Global Analytics"])

CAT = settings.GLUE_DB_CATALOGO
COM = settings.GLUE_DB_COMUNITY


@router.get("/genres/most-watched")
def most_watched_genres(limit: int = Query(default=10, ge=1, le=50)):
    """
    Los géneros con más reproducciones en salas grupales.
    Cruza: catalogo.genre ↔ catalogo.movie_genre ↔ catalogo.movie ↔ comunity.watch_rooms
    """
    sql = f"""
        SELECT
            g.name  AS genre,
            COUNT(wr.id) AS total_reproducciones
        FROM "{CAT}"."genre" g
        JOIN "{CAT}"."movie_genre" mg ON g.id = mg.genre_id
        JOIN "{CAT}"."movie"       m  ON mg.movie_id = m.id
        JOIN "{COM}"."watch_rooms" wr ON wr.movie_id = m.public_id
        GROUP BY g.name
        ORDER BY total_reproducciones DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/actors/most-popular")
def most_popular_actors(
    actor_type: str = Query(default="ACTOR", description="ACTOR o DIRECTOR"),
    limit: int = Query(default=10, ge=1, le=50),
):
    """
    Los actores/directores cuyas películas han sido más reproducidas.
    Cruza: catalogo.artist ↔ catalogo.movie_artist ↔ catalogo.movie ↔ comunity.watch_rooms
    """
    sql = f"""
        SELECT
            a.name  AS artist_name,
            a.type  AS artist_type,
            COUNT(DISTINCT m.id)  AS peliculas_en_catalogo,
            COUNT(wr.id)          AS total_reproducciones
        FROM "{CAT}"."artist" a
        JOIN "{CAT}"."movie_artist" ma ON a.id = ma.artist_id
        JOIN "{CAT}"."movie"        m  ON ma.movie_id = m.id
        LEFT JOIN "{COM}"."watch_rooms" wr ON wr.movie_id = m.public_id
        WHERE UPPER(a.type) = UPPER('{actor_type}')
        GROUP BY a.name, a.type
        ORDER BY total_reproducciones DESC, peliculas_en_catalogo DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/clubs/{club_id}/top-movies")
def club_top_movies(
    club_id: int,
    limit: int = Query(default=10, ge=1, le=50),
):
    """
    Las películas más vistas dentro de un club específico.
    Cruza: comunity.watch_rooms ↔ catalogo.movie (filtrado por club_id)
    """
    sql = f"""
        SELECT
            m.title,
            m.release_year,
            m.rating,
            COUNT(wr.id) AS salas_en_club
        FROM "{COM}"."watch_rooms" wr
        JOIN "{CAT}"."movie" m ON wr.movie_id = m.public_id
        WHERE wr.club_id = '{club_id}'
        GROUP BY m.title, m.release_year, m.rating
        ORDER BY salas_en_club DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/clubs/most-active")
def most_active_clubs(limit: int = Query(default=10, ge=1, le=50)):
    """
    Los clubes con más actividad (salas de reproducción creadas).
    Cruza: comunity.clubs ↔ comunity.watch_rooms ↔ comunity.memberships
    """
    sql = f"""
        SELECT
            c.name          AS club_name,
            c.visibility,
            COUNT(DISTINCT mem.user_id) AS total_miembros,
            COUNT(DISTINCT wr.id)       AS total_salas
        FROM "{COM}"."clubs" c
        LEFT JOIN "{COM}"."memberships"  mem ON c.id = mem.club_id
        LEFT JOIN "{COM}"."watch_rooms"  wr  ON c.id = wr.club_id
        GROUP BY c.name, c.visibility
        ORDER BY total_salas DESC, total_miembros DESC
        LIMIT {limit}
    """
    return _execute(sql)


def _execute(sql: str):
    try:
        return run_query(sql)
    except AthenaQueryError as e:
        raise HTTPException(status_code=500, detail=f"Error en Athena: {e}")
    except AthenaTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Timeout en Athena: {e}")
