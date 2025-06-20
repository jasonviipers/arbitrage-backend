import asyncio
from typing import Dict, List, Any, Optional
import logging
from datetime import datetime, timedelta
import json
from openai import AsyncOpenAI
from app.core.config import settings
from app.models.events import ArbitrageOpportunity, Event, BookmakerStatus
from app.core.database import AsyncSessionLocal
from sqlalchemy import select, and_, update

logger = logging.getLogger(__name__)

class AIAnalyzer:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4"
        
    async def analyze_opportunity(self, opportunity_id: str) -> Dict[str, Any]:
        """Analyze an arbitrage opportunity using AI"""
        async with AsyncSessionLocal() as db:
            try:
                # Get opportunity with related data
                stmt = select(ArbitrageOpportunity).where(ArbitrageOpportunity.id == opportunity_id)
                result = await db.execute(stmt)
                opportunity = result.scalar_one_or_none()
                
                if not opportunity:
                    raise ValueError(f"Opportunity {opportunity_id} not found")
                
                # Get event data
                event_stmt = select(Event).where(Event.id == opportunity.event_id)
                event_result = await db.execute(event_stmt)
                event = event_result.scalar_one_or_none()
                
                if not event:
                    raise ValueError(f"Event {opportunity.event_id} not found")
                
                # Get bookmaker reliability scores
                bookmaker_scores = await self._get_bookmaker_scores(db, opportunity)
                
                # Prepare analysis context
                analysis_context = {
                    "opportunity": {
                        "profit_percentage": opportunity.profit_percentage,
                        "total_stake": opportunity.total_stake,
                        "expected_profit": opportunity.expected_profit,
                        "risk_score": opportunity.risk_score,
                        "market_type": opportunity.market_type,
                        "bookmaker_stakes": opportunity.bookmaker_stakes,
                        "bookmaker_odds": opportunity.bookmaker_odds
                    },
                    "event": {
                        "sport": event.sport,
                        "teams": event.teams,
                        "commence_time": event.commence_time.isoformat(),
                        "time_to_event_hours": (event.commence_time - datetime.utcnow()).total_seconds() / 3600
                    },
                    "bookmaker_reliability": bookmaker_scores,
                    "market_conditions": await self._analyze_market_conditions(db, event)
                }
                
                # Get AI analysis
                ai_analysis = await self._get_ai_analysis(analysis_context)
                
                # Update opportunity with AI analysis
                update_stmt = (
                    update(ArbitrageOpportunity)
                    .where(ArbitrageOpportunity.id == opportunity_id)
                    .values(
                        ai_score=ai_analysis["ai_score"],
                        ai_analysis=ai_analysis,
                        status="analyzed"
                    )
                )
                
                await db.execute(update_stmt)
                await db.commit()
                
                logger.info(f"AI analysis completed for opportunity {opportunity_id}")
                return ai_analysis
                
            except Exception as e:
                await db.rollback()
                logger.error(f"Error analyzing opportunity {opportunity_id}: {e}")
                raise

    async def _get_bookmaker_scores(self, db, opportunity: ArbitrageOpportunity) -> Dict[str, float]:
        """Get reliability scores for bookmakers involved in the opportunity"""
        bookmakers = list(opportunity.bookmaker_stakes.keys())
        scores = {}
        
        for bookmaker in bookmakers:
            stmt = select(BookmakerStatus).where(BookmakerStatus.bookmaker == bookmaker)
            result = await db.execute(stmt)
            status = result.scalar_one_or_none()
            
            if status:
                scores[bookmaker] = status.reliability_score
            else:
                scores[bookmaker] = 5.0  # Default score
        
        return scores

    async def _analyze_market_conditions(self, db, event: Event) -> Dict[str, Any]:
        """Analyze current market conditions for the event"""
        try:
            # Get recent opportunities for similar events
            similar_events_stmt = (
                select(ArbitrageOpportunity)
                .join(Event, ArbitrageOpportunity.event_id == Event.id)
                .where(
                    and_(
                        Event.sport == event.sport,
                        ArbitrageOpportunity.detected_at > datetime.utcnow() - timedelta(days=7)
                    )
                )
                .limit(50)
            )
            
            result = await db.execute(similar_events_stmt)
            recent_opportunities = result.scalars().all()
            
            if not recent_opportunities:
                return {"market_activity": "low", "average_profit": 0, "opportunity_count": 0}
            
            # Calculate market metrics
            profit_percentages = [opp.profit_percentage for opp in recent_opportunities]
            avg_profit = sum(profit_percentages) / len(profit_percentages)
            
            market_activity = "high" if len(recent_opportunities) > 20 else "medium" if len(recent_opportunities) > 10 else "low"
            
            return {
                "market_activity": market_activity,
                "average_profit": round(avg_profit, 2),
                "opportunity_count": len(recent_opportunities),
                "profit_range": {
                    "min": min(profit_percentages),
                    "max": max(profit_percentages)
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing market conditions: {e}")
            return {"market_activity": "unknown", "average_profit": 0, "opportunity_count": 0}

    async def _get_ai_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Get AI analysis using OpenAI"""
        try:
            prompt = self._build_analysis_prompt(context)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert sports betting arbitrage analyst. Analyze the provided opportunity and provide a detailed assessment with scores and recommendations."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            # Parse AI response
            ai_response = response.choices[0].message.content
            analysis = await self._parse_ai_response(ai_response, context)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error getting AI analysis: {e}")
            # Return default analysis if AI fails
            return self._get_default_analysis(context)

    def _build_analysis_prompt(self, context: Dict[str, Any]) -> str:
        """Build the analysis prompt for AI"""
        return f"""
        Analyze this sports betting arbitrage opportunity:

        OPPORTUNITY DETAILS:
        - Profit Percentage: {context['opportunity']['profit_percentage']}%
        - Expected Profit: ${context['opportunity']['expected_profit']}
        - Risk Score: {context['opportunity']['risk_score']}/10
        - Market Type: {context['opportunity']['market_type']}
        - Total Stake Required: ${context['opportunity']['total_stake']}

        EVENT DETAILS:
        - Sport: {context['event']['sport']}
        - Teams: {' vs '.join(context['event']['teams'])}
        - Time to Event: {context['event']['time_to_event_hours']:.1f} hours
        - Event Time: {context['event']['commence_time']}

        BOOKMAKER RELIABILITY:
        {json.dumps(context['bookmaker_reliability'], indent=2)}

        MARKET CONDITIONS:
        {json.dumps(context['market_conditions'], indent=2)}

        STAKES DISTRIBUTION:
        {json.dumps(context['opportunity']['bookmaker_stakes'], indent=2)}

        ODDS:
        {json.dumps(context['opportunity']['bookmaker_odds'], indent=2)}

        Please provide your analysis in the following JSON format:
        {{
            "ai_score": <score from 1-10>,
            "risk_level": <1-5 scale>,
            "execution_difficulty": "<easy|medium|hard>",
            "recommended_action": "<execute|monitor|skip>",
            "confidence": <0.0-1.0>,
            "key_factors": ["factor1", "factor2", "factor3"],
            "warnings": ["warning1", "warning2"],
            "execution_priority": "<high|medium|low>",
            "reasoning": "<detailed explanation>"
        }}

        Consider factors like:
        - Profit margin vs risk
        - Bookmaker reliability
        - Time sensitivity
        - Market volatility
        - Execution complexity
        - Historical performance of similar opportunities
        """

    async def _parse_ai_response(self, ai_response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and validate AI response"""
        try:
            # Try to extract JSON from response
            start_idx = ai_response.find('{')
            end_idx = ai_response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = ai_response[start_idx:end_idx]
                analysis = json.loads(json_str)
                
                # Validate and sanitize the analysis
                analysis = self._validate_analysis(analysis, context)
                return analysis
            else:
                raise ValueError("No JSON found in AI response")
                
        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            return self._get_default_analysis(context)

    def _validate_analysis(self, analysis: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize AI analysis"""
        # Ensure required fields exist with defaults
        validated = {
            "ai_score": max(1, min(10, analysis.get("ai_score", 5))),
            "risk_level": max(1, min(5, analysis.get("risk_level", 3))),
            "execution_difficulty": analysis.get("execution_difficulty", "medium"),
            "recommended_action": analysis.get("recommended_action", "monitor"),
            "confidence": max(0.0, min(1.0, analysis.get("confidence", 0.5))),
            "key_factors": analysis.get("key_factors", [])[:5],  # Limit to 5 factors
            "warnings": analysis.get("warnings", [])[:3],  # Limit to 3 warnings
            "execution_priority": analysis.get("execution_priority", "medium"),
            "reasoning": analysis.get("reasoning", "AI analysis completed")[:500],  # Limit length
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "model_used": self.model
        }
        
        # Validate enum values
        if validated["execution_difficulty"] not in ["easy", "medium", "hard"]:
            validated["execution_difficulty"] = "medium"
            
        if validated["recommended_action"] not in ["execute", "monitor", "skip"]:
            validated["recommended_action"] = "monitor"
            
        if validated["execution_priority"] not in ["high", "medium", "low"]:
            validated["execution_priority"] = "medium"
        
        return validated

    def _get_default_analysis(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Get default analysis when AI fails"""
        opportunity = context['opportunity']
        
        # Simple rule-based scoring
        ai_score = 5.0
        
        if opportunity['profit_percentage'] > 5:
            ai_score += 2
        elif opportunity['profit_percentage'] > 3:
            ai_score += 1
            
        if opportunity['risk_score'] < 3:
            ai_score += 1
        elif opportunity['risk_score'] > 7:
            ai_score -= 2
        
        # Time factor
        time_to_event = context['event']['time_to_event_hours']
        if time_to_event < 2:
            ai_score -= 1
        elif time_to_event > 48:
            ai_score += 1
        
        ai_score = max(1, min(10, ai_score))
        
        return {
            "ai_score": ai_score,
            "risk_level": min(5, max(1, int(opportunity['risk_score'] / 2))),
            "execution_difficulty": "medium",
            "recommended_action": "execute" if ai_score >= 7 else "monitor" if ai_score >= 4 else "skip",
            "confidence": 0.6,
            "key_factors": ["profit_margin", "risk_assessment", "time_factor"],
            "warnings": ["AI analysis unavailable - using rule-based assessment"],
            "execution_priority": "high" if ai_score >= 8 else "medium" if ai_score >= 5 else "low",
            "reasoning": f"Rule-based analysis: {ai_score}/10 score based on profit margin, risk, and timing",
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "model_used": "rule_based_fallback"
        }

    async def batch_analyze_opportunities(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Analyze multiple opportunities in batch"""
        async with AsyncSessionLocal() as db:
            try:
                # Get unanalyzed opportunities
                stmt = (
                    select(ArbitrageOpportunity)
                    .where(
                        and_(
                            ArbitrageOpportunity.status == "detected",
                            ArbitrageOpportunity.expires_at > datetime.utcnow()
                        )
                    )
                    .order_by(ArbitrageOpportunity.profit_percentage.desc())
                    .limit(limit)
                )
                
                result = await db.execute(stmt)
                opportunities = result.scalars().all()
                
                analyses = []
                for opportunity in opportunities:
                    try:
                        analysis = await self.analyze_opportunity(str(opportunity.id))
                        analyses.append({
                            "opportunity_id": str(opportunity.id),
                            "analysis": analysis
                        })
                    except Exception as e:
                        logger.error(f"Error analyzing opportunity {opportunity.id}: {e}")
                        continue
                
                logger.info(f"Batch analysis completed: {len(analyses)} opportunities analyzed")
                return analyses
                
            except Exception as e:
                logger.error(f"Error in batch analysis: {e}")
                return []

# Singleton instance
ai_analyzer = AIAnalyzer()
