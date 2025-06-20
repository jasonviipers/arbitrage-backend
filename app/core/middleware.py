import time
import logging
from typing import Callable
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
import redis.asyncio as redis
from app.core.config import settings
import uuid

logger = logging.getLogger(__name__)

class LoggingMiddleware:
    """Middleware for request/response logging"""
    
    def __init__(self, app):
        self.app = app

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        # Log request
        start_time = time.time()
        logger.info(
            f"Request started - {correlation_id} - {request.method} {request.url.path}",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "client_ip": request.client.host if request.client else None
            }
        )
        
        try:
            response = await call_next(request)
            
            # Log response
            process_time = time.time() - start_time
            logger.info(
                f"Request completed - {correlation_id} - {response.status_code} - {process_time:.3f}s",
                extra={
                    "correlation_id": correlation_id,
                    "status_code": response.status_code,
                    "process_time": process_time
                }
            )
            
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Request failed - {correlation_id} - {str(e)} - {process_time:.3f}s",
                extra={
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "process_time": process_time
                }
            )
            raise

class RateLimitMiddleware:
    """Middleware for API rate limiting"""
    
    def __init__(self, app):
        self.app = app
        self.redis_client = None
        self.requests_per_window = settings.RATE_LIMIT_REQUESTS
        self.window_seconds = settings.RATE_LIMIT_WINDOW

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Initialize Redis client if needed
        if not self.redis_client:
            try:
                self.redis_client = redis.from_url(settings.REDIS_URL)
            except Exception as e:
                logger.warning(f"Redis not available for rate limiting: {e}")
                return await call_next(request)
        
        # Get client identifier
        client_ip = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("authorization")
        
        # Use user ID if authenticated, otherwise use IP
        if auth_header:
            try:
                # Extract user ID from token (simplified)
                client_id = f"user:{auth_header[-10:]}"  # Use last 10 chars of token
            except:
                client_id = f"ip:{client_ip}"
        else:
            client_id = f"ip:{client_ip}"
        
        # Check rate limit
        try:
            current_requests = await self._check_rate_limit(client_id)
            
            if current_requests > self.requests_per_window:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "message": f"Maximum {self.requests_per_window} requests per {self.window_seconds} seconds",
                        "retry_after": self.window_seconds
                    },
                    headers={"Retry-After": str(self.window_seconds)}
                )
            
        except Exception as e:
            logger.warning(f"Rate limiting check failed: {e}")
            # Continue without rate limiting if Redis fails
        
        return await call_next(request)

    async def _check_rate_limit(self, client_id: str) -> int:
        """Check and update rate limit for client"""
        key = f"rate_limit:{client_id}"
        
        try:
            # Use Redis pipeline for atomic operations
            pipe = self.redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.window_seconds)
            results = await pipe.execute()
            
            return results[0]
            
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            return 0  # Allow request if Redis fails
