import asyncio
import aiohttp
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging
from app.core.config import settings
from app.models.events import Event, OddsSnapshot, BookmakerStatus
from app.core.database import AsyncSessionLocal
from sqlalchemy import select, update
import json

logger = logging.getLogger(__name__)

class OddsCollector:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.supported_sports = ["soccer", "americanfootball_nfl", "basketball_nba", "tennis"]
        self.bookmakers = ["bet365", "pinnacle", "betfair", "draftkings", "fanduel"]
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "ArbitrageBot/1.0"}
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def collect_odds_for_sport(self, sport: str) -> List[Dict[str, Any]]:
        """Collect odds for a specific sport from The Odds API"""
        try:
            url = f"{settings.ODDS_API_BASE_URL}/sports/{sport}/odds"
            params = {
                "apiKey": settings.ODDS_API_KEY,
                "regions": "us,uk,eu",
                "markets": "h2h,spreads,totals",
                "oddsFormat": "decimal",
                "dateFormat": "iso"
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Collected {len(data)} events for {sport}")
                    return data
                elif response.status == 429:
                    logger.warning(f"Rate limited for {sport}")
                    await self._handle_rate_limit(response.headers)
                    return []
                else:
                    logger.error(f"API error for {sport}: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error collecting odds for {sport}: {e}")
            return []

    async def _handle_rate_limit(self, headers: Dict[str, str]):
        """Handle rate limiting with exponential backoff"""
        reset_time = headers.get('X-RateLimit-Reset')
        if reset_time:
            wait_time = int(reset_time) - int(datetime.now().timestamp())
            wait_time = max(wait_time, 60)  # Minimum 1 minute wait
            logger.info(f"Rate limited, waiting {wait_time} seconds")
            await asyncio.sleep(wait_time)

    async def normalize_odds_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize odds data from different sources"""
        normalized_events = []
        
        for event_data in raw_data:
            try:
                normalized_event = {
                    "external_id": event_data["id"],
                    "sport": event_data["sport_key"],
                    "teams": [event_data["home_team"], event_data["away_team"]],
                    "commence_time": datetime.fromisoformat(
                        event_data["commence_time"].replace('Z', '+00:00')
                    ),
                    "bookmakers": {}
                }
                
                # Process bookmaker odds
                for bookmaker_data in event_data.get("bookmakers", []):
                    bookmaker_name = bookmaker_data["key"]
                    if bookmaker_name in self.bookmakers:
                        normalized_event["bookmakers"][bookmaker_name] = {
                            "markets": {},
                            "last_update": datetime.fromisoformat(
                                bookmaker_data["last_update"].replace('Z', '+00:00')
                            )
                        }
                        
                        # Process markets
                        for market in bookmaker_data.get("markets", []):
                            market_key = market["key"]
                            outcomes = {}
                            
                            for outcome in market.get("outcomes", []):
                                outcome_key = self._normalize_outcome_key(outcome["name"])
                                outcomes[outcome_key] = float(outcome["price"])
                            
                            normalized_event["bookmakers"][bookmaker_name]["markets"][market_key] = outcomes
                
                if normalized_event["bookmakers"]:  # Only include events with odds
                    normalized_events.append(normalized_event)
                    
            except Exception as e:
                logger.error(f"Error normalizing event data: {e}")
                continue
                
        return normalized_events

    def _normalize_outcome_key(self, outcome_name: str) -> str:
        """Normalize outcome names across bookmakers"""
        outcome_name = outcome_name.lower().strip()
        
        # Common mappings
        mappings = {
            "1": "home",
            "2": "away", 
            "x": "draw",
            "draw": "draw",
            "tie": "draw",
            "over": "over",
            "under": "under"
        }
        
        return mappings.get(outcome_name, outcome_name)

    async def store_events_and_odds(self, normalized_events: List[Dict[str, Any]]):
        """Store events and odds in database"""
        async with AsyncSessionLocal() as db:
            try:
                for event_data in normalized_events:
                    # Upsert event
                    stmt = select(Event).where(Event.external_id == event_data["external_id"])
                    result = await db.execute(stmt)
                    event = result.scalar_one_or_none()
                    
                    if not event:
                        event = Event(
                            external_id=event_data["external_id"],
                            sport=event_data["sport"],
                            teams=event_data["teams"],
                            commence_time=event_data["commence_time"]
                        )
                        db.add(event)
                        await db.flush()
                    
                    # Store odds snapshots
                    for bookmaker, bookmaker_data in event_data["bookmakers"].items():
                        odds_snapshot = OddsSnapshot(
                            event_id=event.id,
                            bookmaker=bookmaker,
                            odds_data=bookmaker_data["markets"],
                            captured_at=bookmaker_data["last_update"]
                        )
                        db.add(odds_snapshot)
                        
                        # Update bookmaker status
                        await self._update_bookmaker_status(db, bookmaker, True)
                
                await db.commit()
                logger.info(f"Stored {len(normalized_events)} events with odds")
                
            except Exception as e:
                await db.rollback()
                logger.error(f"Error storing events and odds: {e}")
                raise

    async def _update_bookmaker_status(self, db, bookmaker: str, success: bool):
        """Update bookmaker status based on API response"""
        stmt = select(BookmakerStatus).where(BookmakerStatus.bookmaker == bookmaker)
        result = await db.execute(stmt)
        status = result.scalar_one_or_none()
        
        if not status:
            status = BookmakerStatus(bookmaker=bookmaker)
            db.add(status)
        
        if success:
            status.api_status = "healthy"
            status.last_successful_fetch = datetime.utcnow()
            status.error_count = 0
        else:
            status.error_count += 1
            if status.error_count > 5:
                status.api_status = "degraded"
            if status.error_count > 20:
                status.api_status = "down"

    async def collect_all_odds(self):
        """Main method to collect odds for all supported sports"""
        logger.info("Starting odds collection cycle")
        
        async with self:
            all_events = []
            
            for sport in self.supported_sports:
                try:
                    raw_odds = await self.collect_odds_for_sport(sport)
                    if raw_odds:
                        normalized_odds = await self.normalize_odds_data(raw_odds)
                        all_events.extend(normalized_odds)
                        
                    # Rate limiting between sports
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error collecting odds for {sport}: {e}")
                    continue
            
            if all_events:
                await self.store_events_and_odds(all_events)
                logger.info(f"Odds collection completed: {len(all_events)} events processed")
            else:
                logger.warning("No odds data collected")

# Singleton instance
odds_collector = OddsCollector()
