from pydantic_settings import BaseSettings
from typing import List, Optional
import os

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost/arbitrage_db"
    REDIS_URL: str = "redis://localhost:6379"
    
    # External APIs
    ODDS_API_KEY: str
    ODDS_API_BASE_URL: str = "https://api.the-odds-api.com/v4"
    OPENAI_API_KEY: str
    BETFAIR_API_KEY: Optional[str] = None
    SMARKETS_API_KEY: Optional[str] = None
    
    # Business Logic
    MIN_ARBITRAGE_PERCENTAGE: float = 2.0
    MAX_STAKE_PERCENTAGE: float = 10.0
    DEFAULT_BANKROLL: float = 10000.0
    KELLY_FRACTION: float = 0.25
    
    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]
    
    # Background Tasks
    ODDS_COLLECTION_INTERVAL: int = 30  # seconds
    ARBITRAGE_DETECTION_INTERVAL: int = 10  # seconds
    
    # Monitoring
    SENTRY_DSN: Optional[str] = None
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
