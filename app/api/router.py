from fastapi import APIRouter

from app.api.routes import movies, users, global_stats, interactions

api_router = APIRouter()

api_router.include_router(movies.router)
api_router.include_router(users.router)
api_router.include_router(global_stats.router)
api_router.include_router(interactions.router)
