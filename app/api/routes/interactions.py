"""
Endpoints de analítica de interacciones (Reviews, Likes, Watchlists, Watch History).
Filtra por partition_1 (fecha) para iteraction y partition_0 para tablas del catálogo.
"""

from fastapi import APIRouter, HTTPException, Query

from app.athena import run_query, partition_filter
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
    Cruza: iteraction(partition_0='reviews') ↔ catalogo.movie
    """
    pf_m = partition_filter("m")              # partition_0 para movie
    pf_r = partition_filter("r", use_iteraction=True)  # partition_1 para iteraction
    sql = f"""
        SELECT 
            m.title,
            m.release_year,
            AVG(CAST(r.score AS DOUBLE)) as average_score,
            COUNT(r.user_id) as total_reviews
        FROM "{CAT}"."movie" m
        JOIN "{ITR}"."iteraction" r
          ON CAST(m.public_id AS VARCHAR) = r.movie_id
         AND r.partition_0 = 'reviews'
         {pf_r}
        WHERE 1=1 {pf_m}
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
    Cruza: iteraction(partition_0='likes') ↔ catalogo.movie
    """
    pf_m = partition_filter("m")
    pf_l = partition_filter("l", use_iteraction=True)
    sql = f"""
        SELECT 
            m.title,
            m.release_year,
            COUNT(l.user_id) as total_likes
        FROM "{CAT}"."movie" m
        JOIN "{ITR}"."iteraction" l
          ON CAST(m.public_id AS VARCHAR) = l.movie_id
         AND l.partition_0 = 'likes'
         {pf_l}
        WHERE 1=1 {pf_m}
        GROUP BY m.title, m.release_year
        ORDER BY total_likes DESC
        LIMIT {limit}
    """
    return _execute(sql)


@router.get("/users/{user_id}/social-activity")
def user_social_activity(user_id: int):
    """
    Resumen de actividad social de un usuario.
    """
    from app.athena.partitions import get_latest_iteraction_partition
    date = get_latest_iteraction_partition()
    date_cond = f"AND partition_1 = '{date}'" if date else ""
    sql = f"""
        SELECT
            (SELECT COUNT(*) FROM "{ITR}"."iteraction"
             WHERE CAST(user_id AS VARCHAR) = '{user_id}' AND partition_0 = 'reviews' {date_cond}) as total_reviews,
            (SELECT COUNT(*) FROM "{ITR}"."iteraction"
             WHERE CAST(user_id AS VARCHAR) = '{user_id}' AND partition_0 = 'likes' {date_cond}) as total_likes,
            (SELECT COUNT(*) FROM "{ITR}"."iteraction"
             WHERE CAST(user_id AS VARCHAR) = '{user_id}' AND partition_0 = 'watchlist' {date_cond}) as total_watchlist,
            (SELECT COUNT(*) FROM "{ITR}"."iteraction"
             WHERE CAST(user_id AS VARCHAR) = '{user_id}' AND partition_0 = 'watch_history'
             AND completed = 'true' {date_cond}) as movies_completed
    """
    return _execute(sql)


@router.get("/movies/most-abandoned")
def most_abandoned_movies(limit: int = Query(default=10, ge=1, le=100)):
    """
    Películas que empezaron a ver pero no terminaron (completed = false).
    """
    pf_m = partition_filter("m")
    pf_w = partition_filter("w", use_iteraction=True)
    sql = f"""
        SELECT 
            m.title,
            m.release_year,
            COUNT(w.user_id) as abandon_count
        FROM "{CAT}"."movie" m
        JOIN "{ITR}"."iteraction" w
          ON CAST(m.public_id AS VARCHAR) = w.movie_id
         AND w.partition_0 = 'watch_history'
         {pf_w}
        WHERE w.completed = 'false' {pf_m}
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
