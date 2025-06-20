from fastapi import APIRouter
from app.api.v1.endpoints import auth, events, opportunities, portfolio, bookmakers, health

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(opportunities.router, prefix="/opportunities", tags=["arbitrage"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
api_router.include_router(bookmakers.router, prefix="/bookmakers", tags=["bookmakers"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
