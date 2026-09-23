from fastapi import APIRouter, HTTPException, Query
from app.athena import run_query, partition_filter
from app.core.config import settings
from app.core.exceptions import AthenaQueryError, AthenaTimeoutError
from app.athena.partitions import get_latest_iteraction_partition, get_latest_partition

router = APIRouter(prefix="/dashboard", tags=["Dashboard Analytics"])

CAT = settings.GLUE_DB_CATALOGO
COM = settings.GLUE_DB_COMUNITY
ITR = settings.GLUE_DB_ITERACTION

def _itr_date() -> str:
    """Returns an extra AND clause for the iteraction partition date filter."""
    from app.athena.partitions import get_latest_iteraction_partition
    d = get_latest_iteraction_partition()
    return f"AND partition_1 = '{d}'" if d else ""

def _cat_date(alias: str = "") -> str:
    """Returns an extra AND/WHERE clause for regular table partition date filter."""
    from app.athena.partitions import get_latest_partition
    d = get_latest_partition()
    if not d:
        return ""
    prefix = f"{alias}." if alias else ""
    return f"AND {prefix}partition_0 = '{d}'"

def _execute(sql: str):
    try:
        return run_query(sql)
    except AthenaQueryError as e:
        raise HTTPException(status_code=500, detail=f"Error en Athena: {e}")
    except AthenaTimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Timeout en Athena: {e}")

@router.get("/kpis")
def get_kpis():
    """
    Platform KPIs summary: total movies, total users, total clubs, total watch rooms, total interactions, average movie rating.
    """
    sql = f"""
    SELECT 
        (SELECT COUNT(1) FROM "{CAT}"."movie" WHERE 1=1 {_cat_date()}) AS total_movies,
        (SELECT COUNT(1) FROM "{COM}"."users" WHERE 1=1 {_cat_date()}) AS total_users,
        (SELECT COUNT(1) FROM "{COM}"."clubs" WHERE 1=1 {_cat_date()}) AS total_clubs,
        (SELECT COUNT(1) FROM "{COM}"."watch_rooms" WHERE 1=1 {_cat_date()}) AS total_watch_rooms,
        (SELECT COUNT(1) FROM "{ITR}"."iteraction" WHERE 1=1 {_itr_date()}) AS total_interactions,
        (SELECT AVG(CAST(rating AS DOUBLE)) FROM "{CAT}"."movie" WHERE 1=1 {_cat_date()}) AS avg_movie_rating
    """
    return _execute(sql)

@router.get("/engagement-funnel")
def get_engagement_funnel():
    """
    User engagement funnel: registered users -> club members -> watch room participants -> reviewers.
    """
    sql = f"""
    SELECT 
        (SELECT COUNT(1) FROM "{COM}"."users") AS registered_users,
        (SELECT COUNT(DISTINCT user_id) FROM "{COM}"."memberships") AS users_in_clubs,
        (SELECT COUNT(DISTINCT user_id) FROM "{COM}"."watch_participants") AS users_in_watch_rooms,
        (SELECT COUNT(DISTINCT user_id) FROM "{ITR}"."iteraction" WHERE partition_0 = 'reviews') AS reviewers
    """
    return _execute(sql)

@router.get("/genre-engagement")
def get_genre_engagement():
    """
    Genre engagement matrix: total movies, watch rooms, avg rating, reviews, and likes per genre.
    """
    sql = f"""
    WITH movie_stats AS (
        SELECT 
            m.id as movie_id,
            m.rating as avg_rating,
            (SELECT COUNT(DISTINCT id) FROM "{COM}"."watch_rooms" WHERE movie_id = CAST(m.public_id AS VARCHAR) {_cat_date()}) as watch_rooms,
            (SELECT COUNT(1) FROM "{ITR}"."iteraction" WHERE movie_id = CAST(m.public_id AS VARCHAR) AND partition_0 = 'reviews' {_itr_date()}) as total_reviews,
            (SELECT COUNT(1) FROM "{ITR}"."iteraction" WHERE movie_id = CAST(m.public_id AS VARCHAR) AND partition_0 = 'likes' {_itr_date()}) as total_likes
        FROM "{CAT}"."movie" m WHERE 1=1 {_cat_date("m")}
    )
    SELECT 
        g.name as genre_name,
        COUNT(DISTINCT mg.movie_id) as total_movies,
        SUM(ms.watch_rooms) as total_watch_rooms,
        AVG(ms.avg_rating) as avg_rating,
        SUM(ms.total_reviews) as total_reviews,
        SUM(ms.total_likes) as total_likes
    FROM "{CAT}"."genre" g
    JOIN "{CAT}"."movie_genre" mg ON g.id = mg.genre_id
    JOIN movie_stats ms ON mg.movie_id = ms.movie_id
    WHERE 1=1 {_cat_date("g")} {_cat_date("mg")}
    GROUP BY g.name
    ORDER BY total_watch_rooms DESC
    """
    return _execute(sql)

@router.get("/peak-hours")
def get_peak_hours():
    """
    Activity distribution: hour with most activity based on watch room creation.
    """
    sql = f"""
    SELECT 
        EXTRACT(hour FROM CAST(created_at AS TIMESTAMP)) AS hour_of_day,
        COUNT(1) AS activity_count
    FROM "{COM}"."watch_rooms"
    WHERE 1=1 {_cat_date()}
    GROUP BY 1
    ORDER BY hour_of_day
    """
    return _execute(sql)

@router.get("/user-retention-cohort")
def get_user_retention_cohort():
    """
    User retention: users grouped by registration month, showing active users in subsequent months.
    """
    sql = f"""
    WITH cohort AS (
        SELECT 
            id AS user_id, 
            DATE_TRUNC('month', CAST(created_at AS TIMESTAMP)) AS cohort_month 
        FROM "{COM}"."users" WHERE 1=1 {_cat_date()}
    ),
    activity AS (
        SELECT 
            user_id,
            DATE_TRUNC('month', CAST(created_at AS TIMESTAMP)) AS activity_month
        FROM (
            SELECT user_id, joined_at as created_at FROM "{COM}"."watch_participants" WHERE 1=1 {_cat_date()}
            UNION ALL
            SELECT user_id, created_at FROM "{ITR}"."iteraction" WHERE 1=1 {_itr_date()}
        ) active_events
    )
    SELECT 
        c.cohort_month,
        a.activity_month,
        COUNT(DISTINCT c.user_id) AS active_users
    FROM cohort c
    JOIN activity a ON CAST(c.user_id AS VARCHAR) = CAST(a.user_id AS VARCHAR)
    WHERE a.activity_month >= c.cohort_month
    GROUP BY c.cohort_month, a.activity_month
    ORDER BY c.cohort_month, a.activity_month
    """
    return _execute(sql)

@router.get("/content-gap-analysis")
def get_content_gap_analysis():
    """
    Content gap: genres with high engagement (watch rooms) but low catalog count.
    """
    sql = f"""
    SELECT 
        g.name AS genre_name,
        COUNT(DISTINCT mg.movie_id) AS total_movies,
        COUNT(DISTINCT wr.id) AS total_watch_rooms,
        CAST(COUNT(DISTINCT wr.id) AS DOUBLE) / NULLIF(COUNT(DISTINCT mg.movie_id), 0) AS engagement_ratio
    FROM "{CAT}"."genre" g
    JOIN "{CAT}"."movie_genre" mg ON g.id = mg.genre_id
    JOIN "{CAT}"."movie" m ON mg.movie_id = m.id
    LEFT JOIN "{COM}"."watch_rooms" wr ON CAST(wr.movie_id AS VARCHAR) = CAST(m.public_id AS VARCHAR)
    WHERE 1=1 {_cat_date("g")} {_cat_date("mg")} {_cat_date("m")} {_cat_date("wr")}
    GROUP BY g.name
    ORDER BY engagement_ratio DESC
    """
    return _execute(sql)

@router.get("/club-health")
def get_club_health():
    """
    Club health metrics: member count, activity ratio, diversity of movies watched, average rating of movies chosen.
    """
    sql = f"""
    SELECT 
        c.name AS club_name,
        COUNT(DISTINCT m.user_id) AS member_count,
        COUNT(DISTINCT wr.id) AS total_watch_rooms,
        CAST(COUNT(DISTINCT wr.id) AS DOUBLE) / NULLIF(COUNT(DISTINCT m.user_id), 0) AS activity_ratio,
        COUNT(DISTINCT wr.movie_id) AS unique_movies_watched,
        AVG(mo.rating) AS avg_movie_rating
    FROM "{COM}"."clubs" c
    LEFT JOIN "{COM}"."memberships" m ON c.id = m.club_id
    LEFT JOIN "{COM}"."watch_rooms" wr ON CAST(c.id AS VARCHAR) = CAST(wr.club_id AS VARCHAR)
    LEFT JOIN "{CAT}"."movie" mo ON CAST(wr.movie_id AS VARCHAR) = CAST(mo.public_id AS VARCHAR)
    WHERE 1=1 {_cat_date("c")} {_cat_date("m")} {_cat_date("wr")} {_cat_date("mo")}
    GROUP BY c.name
    ORDER BY activity_ratio DESC
    """
    return _execute(sql)

@router.get("/movie-lifecycle")
def get_movie_lifecycle():
    """
    Movie lifecycle analysis: relationship between catalog rating, user reviews score, likes count, and watch room count.
    """
    sql = f"""
    WITH movie_metrics AS (
        SELECT 
            m.id as movie_id,
            m.public_id,
            m.title,
            m.rating AS catalog_rating,
            (SELECT AVG(CAST(score AS DOUBLE)) FROM "{ITR}"."iteraction" WHERE movie_id = CAST(m.public_id AS VARCHAR) AND partition_0 = 'reviews' {_itr_date()}) AS avg_user_review_score,
            (SELECT COUNT(1) FROM "{ITR}"."iteraction" WHERE movie_id = CAST(m.public_id AS VARCHAR) AND partition_0 = 'likes' {_itr_date()}) AS likes_count,
            (SELECT COUNT(1) FROM "{COM}"."watch_rooms" WHERE movie_id = CAST(m.public_id AS VARCHAR) {_cat_date()}) AS watch_room_count
        FROM "{CAT}"."movie" m WHERE 1=1 {_cat_date("m")}
    )
    SELECT * FROM movie_metrics
    ORDER BY watch_room_count DESC
    LIMIT 100
    """
    return _execute(sql)

@router.get("/raw")
def get_raw(sql: str = Query(...)):
    return _execute(sql)
