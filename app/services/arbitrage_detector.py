import asyncio
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import logging
import math
from app.core.config import settings
from app.models.events import Event, OddsSnapshot, ArbitrageOpportunity
from app.core.database import AsyncSessionLocal
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

class ArbitrageDetector:
    def __init__(self):
        self.min_profit_percentage = settings.MIN_ARBITRAGE_PERCENTAGE
        self.max_stake_percentage = settings.MAX_STAKE_PERCENTAGE
        self.kelly_fraction = settings.KELLY_FRACTION

    async def detect_arbitrage_opportunities(self) -> List[Dict[str, Any]]:
        """Main method to detect arbitrage opportunities"""
        logger.info("Starting arbitrage detection cycle")
        
        opportunities = []
        
        async with AsyncSessionLocal() as db:
            try:
                # Get recent events with odds
                cutoff_time = datetime.utcnow() - timedelta(minutes=10)
                
                stmt = (
                    select(Event)
                    .where(
                        and_(
                            Event.status == "upcoming",
                            Event.commence_time > datetime.utcnow(),
                            Event.commence_time < datetime.utcnow() + timedelta(days=7)
                        )
                    )
                    .order_by(Event.commence_time)
                    .limit(100)
                )
                
                result = await db.execute(stmt)
                events = result.scalars().all()
                
                for event in events:
                    try:
                        event_opportunities = await self._analyze_event_for_arbitrage(db, event)
                        opportunities.extend(event_opportunities)
                    except Exception as e:
                        logger.error(f"Error analyzing event {event.id}: {e}")
                        continue
                
                # Store detected opportunities
                if opportunities:
                    await self._store_opportunities(db, opportunities)
                
                logger.info(f"Arbitrage detection completed: {len(opportunities)} opportunities found")
                return opportunities
                
            except Exception as e:
                logger.error(f"Error in arbitrage detection: {e}")
                return []

    async def _analyze_event_for_arbitrage(self, db, event: Event) -> List[Dict[str, Any]]:
        """Analyze a single event for arbitrage opportunities"""
        opportunities = []
        
        # Get latest odds for this event
        stmt = (
            select(OddsSnapshot)
            .where(
                and_(
                    OddsSnapshot.event_id == event.id,
                    OddsSnapshot.is_active == True,
                    OddsSnapshot.captured_at > datetime.utcnow() - timedelta(minutes=30)
                )
            )
            .order_by(desc(OddsSnapshot.captured_at))
        )
        
        result = await db.execute(stmt)
        odds_snapshots = result.scalars().all()
        
        if len(odds_snapshots) < 2:
            return opportunities
        
        # Group odds by market type
        odds_by_market = {}
        for snapshot in odds_snapshots:
            for market_type, market_odds in snapshot.odds_data.items():
                if market_type not in odds_by_market:
                    odds_by_market[market_type] = {}
                
                odds_by_market[market_type][snapshot.bookmaker] = {
                    'odds': market_odds,
                    'timestamp': snapshot.captured_at
                }
        
        # Analyze each market for arbitrage
        for market_type, market_data in odds_by_market.items():
            if len(market_data) >= 2:  # Need at least 2 bookmakers
                arb_opportunity = await self._calculate_arbitrage(
                    event, market_type, market_data
                )
                if arb_opportunity:
                    opportunities.append(arb_opportunity)
        
        return opportunities

    async def _calculate_arbitrage(self, event: Event, market_type: str, market_data: Dict) -> Optional[Dict[str, Any]]:
        """Calculate arbitrage for a specific market"""
        try:
            # Get all possible outcomes for this market
            all_outcomes = set()
            for bookmaker_data in market_data.values():
                all_outcomes.update(bookmaker_data['odds'].keys())
            
            if len(all_outcomes) < 2:
                return None
            
            # Find best odds for each outcome
            best_odds = {}
            best_bookmakers = {}
            
            for outcome in all_outcomes:
                best_odd = 0
                best_bookmaker = None
                
                for bookmaker, bookmaker_data in market_data.items():
                    odds = bookmaker_data['odds'].get(outcome, 0)
                    if odds > best_odd:
                        best_odd = odds
                        best_bookmaker = bookmaker
                
                if best_odd > 0:
                    best_odds[outcome] = best_odd
                    best_bookmakers[outcome] = best_bookmaker
            
            if len(best_odds) != len(all_outcomes):
                return None
            
            # Calculate arbitrage
            implied_probabilities = {outcome: 1/odds for outcome, odds in best_odds.items()}
            total_implied_probability = sum(implied_probabilities.values())
            
            # Check if arbitrage exists
            if total_implied_probability >= 1.0:
                return None
            
            profit_percentage = ((1 - total_implied_probability) / total_implied_probability) * 100
            
            if profit_percentage < self.min_profit_percentage:
                return None
            
            # Calculate optimal stakes
            total_stake = 1000  # Base stake for calculation
            stakes = {}
            
            for outcome, probability in implied_probabilities.items():
                stake = (probability / total_implied_probability) * total_stake
                stakes[outcome] = round(stake, 2)
            
            # Calculate expected profit
            expected_profit = total_stake * (profit_percentage / 100)
            
            # Build opportunity data
            opportunity = {
                'event_id': event.id,
                'market_type': market_type,
                'profit_percentage': round(profit_percentage, 2),
                'total_stake': total_stake,
                'expected_profit': round(expected_profit, 2),
                'bookmaker_stakes': {},
                'bookmaker_odds': {},
                'risk_score': await self._calculate_risk_score(event, market_data),
                'expires_at': datetime.utcnow() + timedelta(minutes=15)  # Opportunities expire quickly
            }
            
            # Organize stakes and odds by bookmaker
            for outcome in all_outcomes:
                bookmaker = best_bookmakers[outcome]
                if bookmaker not in opportunity['bookmaker_stakes']:
                    opportunity['bookmaker_stakes'][bookmaker] = {}
                    opportunity['bookmaker_odds'][bookmaker] = {}
                
                opportunity['bookmaker_stakes'][bookmaker][outcome] = stakes[outcome]
                opportunity['bookmaker_odds'][bookmaker][outcome] = best_odds[outcome]
            
            return opportunity
            
        except Exception as e:
            logger.error(f"Error calculating arbitrage: {e}")
            return None

    async def _calculate_risk_score(self, event: Event, market_data: Dict) -> float:
        """Calculate risk score for an opportunity (1-10 scale)"""
        risk_score = 5.0  # Base risk
        
        try:
            # Time to event factor
            time_to_event = (event.commence_time - datetime.utcnow()).total_seconds() / 3600
            if time_to_event < 1:  # Less than 1 hour
                risk_score += 2
            elif time_to_event < 24:  # Less than 24 hours
                risk_score += 1
            elif time_to_event > 168:  # More than 1 week
                risk_score += 1
            
            # Number of bookmakers factor
            num_bookmakers = len(market_data)
            if num_bookmakers >= 4:
                risk_score -= 1
            elif num_bookmakers == 2:
                risk_score += 1
            
            # Odds age factor
            oldest_odds_age = 0
            for bookmaker_data in market_data.values():
                age_minutes = (datetime.utcnow() - bookmaker_data['timestamp']).total_seconds() / 60
                oldest_odds_age = max(oldest_odds_age, age_minutes)
            
            if oldest_odds_age > 10:
                risk_score += 1
            if oldest_odds_age > 30:
                risk_score += 2
            
            # Sport-specific risk
            if event.sport in ['tennis', 'basketball_nba']:
                risk_score += 0.5  # More volatile sports
            
            return min(max(risk_score, 1.0), 10.0)
            
        except Exception as e:
            logger.error(f"Error calculating risk score: {e}")
            return 5.0

    async def _store_opportunities(self, db, opportunities: List[Dict[str, Any]]):
        """Store detected arbitrage opportunities"""
        try:
            for opp_data in opportunities:
                # Check if similar opportunity already exists
                stmt = (
                    select(ArbitrageOpportunity)
                    .where(
                        and_(
                            ArbitrageOpportunity.event_id == opp_data['event_id'],
                            ArbitrageOpportunity.market_type == opp_data['market_type'],
                            ArbitrageOpportunity.status.in_(['detected', 'analyzed']),
                            ArbitrageOpportunity.detected_at > datetime.utcnow() - timedelta(hours=1)
                        )
                    )
                )
                
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if not existing:
                    opportunity = ArbitrageOpportunity(**opp_data)
                    db.add(opportunity)
            
            await db.commit()
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error storing opportunities: {e}")
            raise

    async def calculate_kelly_stakes(self, opportunity: Dict[str, Any], bankroll: float) -> Dict[str, Any]:
        """Calculate optimal stakes using Kelly Criterion"""
        try:
            total_stake = 0
            kelly_stakes = {}
            
            for bookmaker, outcomes in opportunity['bookmaker_odds'].items():
                for outcome, odds in outcomes.items():
                    # Kelly formula: f = (bp - q) / b
                    # where b = odds - 1, p = true probability, q = 1 - p
                    
                    # Estimate true probability (simplified)
                    implied_prob = 1 / odds
                    true_prob = implied_prob * 1.05  # Slight edge assumption
                    
                    if true_prob > 1:
                        true_prob = 0.95
                    
                    b = odds - 1
                    f = (b * true_prob - (1 - true_prob)) / b
                    
                    # Apply Kelly fraction for safety
                    f = f * self.kelly_fraction
                    
                    # Calculate stake
                    if f > 0:
                        stake = bankroll * f * (self.max_stake_percentage / 100)
                        kelly_stakes[f"{bookmaker}_{outcome}"] = max(stake, 10)  # Minimum $10
                        total_stake += stake
            
            return {
                'kelly_stakes': kelly_stakes,
                'total_kelly_stake': total_stake,
                'bankroll_percentage': (total_stake / bankroll) * 100
            }
            
        except Exception as e:
            logger.error(f"Error calculating Kelly stakes: {e}")
            return {'kelly_stakes': {}, 'total_kelly_stake': 0, 'bankroll_percentage': 0}

# Singleton instance
arbitrage_detector = ArbitrageDetector()
