"""
Endpoints de analítica de usuarios.

Responde preguntas como: ¿Cuáles son las películas favoritas de un usuario?
¿Qué géneros prefiere? ¿En qué clubes es más activo?
"""

from fastapi import APIRouter, HTTPException, Query

from app.athena import run_query
from app.core.config import settings
from app.core.exceptions import AthenaQueryError, AthenaTimeoutError

router = APIRouter(prefix="/users", tags=["Users Analytics"])

CAT = settings.GLUE_DB_CATALOGO
COM = settings.GLUE_DB_COMUNITY


@router.get("/{user_id}/favorite-movies")
def user_favorite_movies(
    user_id: int,
    limit: int = Query(default=10, ge=1, le=50),
):
    """
    Las películas favoritas de un usuario: las que más veces ha reproducido en salas.
    Cruza: comunity.watch_rooms ↔ catalogo.movie (filtrado por host_user_id)
    """
    sql = f"""
        SELECT
            m.title,
            m.release_year,
            m.rating,
            COUNT(wr.id) AS veces_en_sala
        FROM "{COM}"."watch_rooms" wr
        JOIN "{CAT}"."movie" m ON wr.movie_id = m.public_id
        WHERE wr.host_user_id = '{user_id}'
        GROUP BY m.title, m.release_year, m.rating
        ORDER BY veces_en_sala DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/{user_id}/favorite-genres")
def user_favorite_genres(user_id: int):
    """
    Los géneros favoritos de un usuario según las películas que ha reproducido.
    Cruza: comunity.watch_rooms ↔ catalogo.movie ↔ catalogo.movie_genre ↔ catalogo.genre
    """
    sql = f"""
        SELECT
            g.name  AS genre,
            COUNT(wr.id) AS veces_en_sala
        FROM "{COM}"."watch_rooms" wr
        JOIN "{CAT}"."movie"       m  ON wr.movie_id = m.public_id
        JOIN "{CAT}"."movie_genre" mg ON m.id = mg.movie_id
        JOIN "{CAT}"."genre"       g  ON mg.genre_id = g.id
        WHERE wr.host_user_id = '{user_id}'
        GROUP BY g.name
        ORDER BY veces_en_sala DESC
    """
    return _execute(sql)


@router.get("/{user_id}/favorite-actors")
def user_favorite_actors(
    user_id: int,
    limit: int = Query(default=10, ge=1, le=50),
):
    """
    Los actores/directores que más aparecen en las películas vistas por un usuario.
    Cruza: comunity.watch_rooms ↔ catalogo.movie ↔ catalogo.movie_artist ↔ catalogo.artist
    """
    sql = f"""
        SELECT
            a.name      AS artist_name,
            a.type      AS artist_type,
            COUNT(wr.id) AS apariciones_en_salas
        FROM "{COM}"."watch_rooms" wr
        JOIN "{CAT}"."movie"        m  ON wr.movie_id = m.public_id
        JOIN "{CAT}"."movie_artist" ma ON m.id = ma.movie_id
        JOIN "{CAT}"."artist"       a  ON ma.artist_id = a.id
        WHERE wr.host_user_id = '{user_id}'
        GROUP BY a.name, a.type
        ORDER BY apariciones_en_salas DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/{user_id}/clubs-activity")
def user_clubs_activity(user_id: int):
    """
    Los clubes a los que pertenece un usuario y cuántas salas se han creado en cada uno.
    Cruza: comunity.memberships ↔ comunity.clubs ↔ comunity.watch_rooms
    """
    sql = f"""
        SELECT
            c.name          AS club_name,
            c.visibility,
            mem.role        AS user_role,
            COUNT(wr.id)    AS salas_creadas
        FROM "{COM}"."memberships" mem
        JOIN "{COM}"."clubs"       c  ON mem.club_id = c.id
        LEFT JOIN "{COM}"."watch_rooms" wr ON wr.club_id = c.id
        WHERE mem.user_id = '{user_id}'
        GROUP BY c.name, c.visibility, mem.role
        ORDER BY salas_creadas DESC
    """
    return _execute(sql)


def _execute(sql: str):
    try:
        return run_query(sql)
    except AthenaQueryError as e:
        raise HTTPException(status_code=500, detail=f"Error en Athena: {e}")
    except AthenaTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Timeout en Athena: {e}")
