"""
Endpoints de analítica de interacciones (Reviews, Likes, Watchlists, Watch History).

Cruza la Glue DB 'iteraction' con 'catalogo' y 'comunity'.
"""

from fastapi import APIRouter, HTTPException, Query

from app.athena import run_query
from app.core.config import settings
from app.core.exceptions import AthenaQueryError, AthenaTimeoutError

router = APIRouter(prefix="/interactions", tags=["Interactions Analytics"])

CAT = settings.GLUE_DB_CATALOGO
COM = settings.GLUE_DB_COMUNITY
ITR = settings.GLUE_DB_ITERACTION

@router.get("/movies/best-rated")
def best_rated_movies(limit: int = Query(default=10, ge=1, le=100)):
    """
    Las películas mejor calificadas por los usuarios (promedio de reviews).
    Cruza: iteraction.reviews ↔ catalogo.movie
    """
    sql = f"""
        SELECT 
            m.title,
            m.release_year,
            AVG(CAST(r.score AS DOUBLE)) as average_score,
            COUNT(r.user_id) as total_reviews
        FROM "{CAT}"."movie" m
        JOIN "{ITR}"."iteraction" r ON CAST(m.public_id AS VARCHAR) = r.movie_id AND r.partition_0 = \'reviews\'
        GROUP BY m.title, m.release_year
        HAVING COUNT(r.user_id) > 5
        ORDER BY average_score DESC, total_reviews DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/movies/most-liked")
def most_liked_movies(limit: int = Query(default=10, ge=1, le=100)):
    """
    Las películas con más likes.
    Cruza: iteraction.likes ↔ catalogo.movie
    """
    sql = f"""
        SELECT 
            m.title,
            m.release_year,
            COUNT(l.user_id) as total_likes
        FROM "{CAT}"."movie" m
        JOIN "{ITR}"."iteraction" l ON CAST(m.public_id AS VARCHAR) = l.movie_id AND l.partition_0 = \'likes\'
        GROUP BY m.title, m.release_year
        ORDER BY total_likes DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/users/{user_id}/social-activity")
def user_social_activity(user_id: int):
    """
    Resumen de actividad social de un usuario: cantidad de reviews, likes, peliculas en watchlist.
    """
    sql = f"""
        SELECT
            (SELECT COUNT(*) FROM "{ITR}"."iteraction" WHERE CAST(user_id AS VARCHAR) = \'{user_id}\' AND partition_0 = \'reviews\') as total_reviews,
            (SELECT COUNT(*) FROM "{ITR}"."iteraction" WHERE CAST(user_id AS VARCHAR) = \'{user_id}\' AND partition_0 = \'likes\') as total_likes,
            (SELECT COUNT(*) FROM "{ITR}"."iteraction" WHERE CAST(user_id AS VARCHAR) = \'{user_id}\' AND partition_0 = \'watchlist\') as total_watchlist,
            (SELECT COUNT(*) FROM "{ITR}"."iteraction" WHERE CAST(user_id AS VARCHAR) = \'{user_id}\' AND partition_0 = \'watch_history\' AND completed = \'true\') as movies_completed
    """
    return _execute(sql)


@router.get("/movies/most-abandoned")
def most_abandoned_movies(limit: int = Query(default=10, ge=1, le=100)):
    """
    Películas que empezaron a ver pero no terminaron (completed = false).
    Cruza: iteraction.watch_history ↔ catalogo.movie
    """
    sql = f"""
        SELECT 
            m.title,
            m.release_year,
            COUNT(w.user_id) as abandon_count
        FROM "{CAT}"."movie" m
        JOIN "{ITR}"."iteraction" w ON CAST(m.public_id AS VARCHAR) = w.movie_id AND w.partition_0 = \'watch_history\'
        WHERE w.completed = \'false\'
        GROUP BY m.title, m.release_year
        ORDER BY abandon_count DESC
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
