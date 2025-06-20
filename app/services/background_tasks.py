import asyncio
import logging
from datetime import datetime, timedelta
from app.core.config import settings
from app.services.odds_collector import odds_collector
from app.services.arbitrage_detector import arbitrage_detector
from app.services.ai_analyzer import ai_analyzer

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    def __init__(self):
        self.tasks = []
        self.running = False
    
    async def start_all_tasks(self):
        """Start all background tasks"""
        if self.running:
            logger.warning("Background tasks already running")
            return
        
        self.running = True
        logger.info("Starting background tasks...")
        
        # Start odds collection task
        odds_task = asyncio.create_task(self._odds_collection_loop())
        self.tasks.append(odds_task)
        
        # Start arbitrage detection task
        arbitrage_task = asyncio.create_task(self._arbitrage_detection_loop())
        self.tasks.append(arbitrage_task)
        
        # Start AI analysis task
        ai_task = asyncio.create_task(self._ai_analysis_loop())
        self.tasks.append(ai_task)
        
        # Start cleanup task
        cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.tasks.append(cleanup_task)
        
        logger.info(f"Started {len(self.tasks)} background tasks")
    
    async def stop_all_tasks(self):
        """Stop all background tasks"""
        self.running = False
        logger.info("Stopping background tasks...")
        
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        self.tasks.clear()
        logger.info("All background tasks stopped")
    
    async def _odds_collection_loop(self):
        """Background task for collecting odds data"""
        logger.info("Starting odds collection loop")
        
        while self.running:
            try:
                await odds_collector.collect_all_odds()
                await asyncio.sleep(settings.ODDS_COLLECTION_INTERVAL)
            except asyncio.CancelledError:
                logger.info("Odds collection task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in odds collection loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _arbitrage_detection_loop(self):
        """Background task for detecting arbitrage opportunities"""
        logger.info("Starting arbitrage detection loop")
        
        while self.running:
            try:
                await arbitrage_detector.detect_arbitrage_opportunities()
                await asyncio.sleep(settings.ARBITRAGE_DETECTION_INTERVAL)
            except asyncio.CancelledError:
                logger.info("Arbitrage detection task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in arbitrage detection loop: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def _ai_analysis_loop(self):
        """Background task for AI analysis of opportunities"""
        logger.info("Starting AI analysis loop")
        
        while self.running:
            try:
                await ai_analyzer.batch_analyze_opportunities(limit=5)
                await asyncio.sleep(60)  # Run every minute
            except asyncio.CancelledError:
                logger.info("AI analysis task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in AI analysis loop: {e}")
                await asyncio.sleep(120)  # Wait before retrying
    
    async def _cleanup_loop(self):
        """Background task for cleaning up old data"""
        logger.info("Starting cleanup loop")
        
        while self.running:
            try:
                await self._cleanup_expired_opportunities()
                await self._cleanup_old_odds_snapshots()
                await asyncio.sleep(3600)  # Run every hour
            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(1800)  # Wait before retrying
    
    async def _cleanup_expired_opportunities(self):
        """Clean up expired arbitrage opportunities"""
        from app.core.database import AsyncSessionLocal
        from app.models.events import ArbitrageOpportunity
        from sqlalchemy import update, and_
        
        async with AsyncSessionLocal() as db:
            try:
                # Mark expired opportunities
                stmt = (
                    update(ArbitrageOpportunity)
                    .where(
                        and_(
                            ArbitrageOpportunity.expires_at <= datetime.utcnow(),
                            ArbitrageOpportunity.status.in_(["detected", "analyzed"])
                        )
                    )
                    .values(status="expired")
                )
                
                result = await db.execute(stmt)
                await db.commit()
                
                if result.rowcount > 0:
                    logger.info(f"Marked {result.rowcount} opportunities as expired")
                    
            except Exception as e:
                await db.rollback()
                logger.error(f"Error cleaning up expired opportunities: {e}")
    
    async def _cleanup_old_odds_snapshots(self):
        """Clean up old odds snapshots"""
        from app.core.database import AsyncSessionLocal
        from app.models.events import OddsSnapshot
        from sqlalchemy import delete
        
        async with AsyncSessionLocal() as db:
            try:
                # Delete odds snapshots older than 7 days
                cutoff_date = datetime.utcnow() - timedelta(days=7)
                
                stmt = delete(OddsSnapshot).where(OddsSnapshot.captured_at < cutoff_date)
                result = await db.execute(stmt)
                await db.commit()
                
                if result.rowcount > 0:
                    logger.info(f"Deleted {result.rowcount} old odds snapshots")
                    
            except Exception as e:
                await db.rollback()
                logger.error(f"Error cleaning up old odds snapshots: {e}")

# Global instance
background_task_manager = BackgroundTaskManager()

async def start_background_tasks():
    """Start all background tasks"""
    await background_task_manager.start_all_tasks()

async def stop_background_tasks():
    """Stop all background tasks"""
    await background_task_manager.stop_all_tasks()
