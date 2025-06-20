from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from app.core.database import get_db
from app.models.events import ArbitrageOpportunity, Event
from app.services.ai_analyzer import ai_analyzer
from app.api.v1.schemas.opportunities import (
    OpportunityResponse, 
    OpportunityListResponse,
    OpportunityAnalysisRequest,
    OpportunityAnalysisResponse
)
from app.core.security import get_current_user

router = APIRouter()

@router.get("/", response_model=OpportunityListResponse)
async def list_opportunities(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    min_profit: Optional[float] = Query(None, ge=0),
    max_risk: Optional[float] = Query(None, ge=1, le=10),
    sport: Optional[str] = Query(None),
    status: Optional[str] = Query("detected"),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List arbitrage opportunities with filtering"""
    try:
        # Build query conditions
        conditions = [ArbitrageOpportunity.expires_at > datetime.utcnow()]
        
        if min_profit is not None:
            conditions.append(ArbitrageOpportunity.profit_percentage >= min_profit)
        
        if max_risk is not None:
            conditions.append(ArbitrageOpportunity.risk_score <= max_risk)
            
        if status:
            conditions.append(ArbitrageOpportunity.status == status)
        
        # Join with events for sport filtering
        query = (
            select(ArbitrageOpportunity, Event)
            .join(Event, ArbitrageOpportunity.event_id == Event.id)
            .where(and_(*conditions))
        )
        
        if sport:
            query = query.where(Event.sport == sport)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total = count_result.scalar()
        
        # Get paginated results
        query = query.order_by(desc(ArbitrageOpportunity.profit_percentage)).offset(skip).limit(limit)
        result = await db.execute(query)
        opportunities_with_events = result.all()
        
        # Format response
        opportunities = []
        for opp, event in opportunities_with_events:
            opp_dict = {
                "id": str(opp.id),
                "event_id": str(opp.event_id),
                "market_type": opp.market_type,
                "profit_percentage": opp.profit_percentage,
                "expected_profit": opp.expected_profit,
                "total_stake": opp.total_stake,
                "risk_score": opp.risk_score,
                "ai_score": opp.ai_score,
                "status": opp.status,
                "detected_at": opp.detected_at,
                "expires_at": opp.expires_at,
                "bookmaker_stakes": opp.bookmaker_stakes,
                "bookmaker_odds": opp.bookmaker_odds,
                "event": {
                    "sport": event.sport,
                    "teams": event.teams,
                    "commence_time": event.commence_time
                }
            }
            opportunities.append(opp_dict)
        
        return OpportunityListResponse(
            opportunities=opportunities,
            total=total,
            skip=skip,
            limit=limit
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching opportunities: {str(e)}")

@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get a specific arbitrage opportunity"""
    try:
        opportunity_uuid = uuid.UUID(opportunity_id)
        
        query = (
            select(ArbitrageOpportunity, Event)
            .join(Event, ArbitrageOpportunity.event_id == Event.id)
            .where(ArbitrageOpportunity.id == opportunity_uuid)
        )
        
        result = await db.execute(query)
        opp_with_event = result.first()
        
        if not opp_with_event:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        
        opp, event = opp_with_event
        
        return OpportunityResponse(
            id=str(opp.id),
            event_id=str(opp.event_id),
            market_type=opp.market_type,
            profit_percentage=opp.profit_percentage,
            expected_profit=opp.expected_profit,
            total_stake=opp.total_stake,
            risk_score=opp.risk_score,
            ai_score=opp.ai_score,
            ai_analysis=opp.ai_analysis,
            status=opp.status,
            detected_at=opp.detected_at,
            expires_at=opp.expires_at,
            bookmaker_stakes=opp.bookmaker_stakes,
            bookmaker_odds=opp.bookmaker_odds,
            event={
                "sport": event.sport,
                "teams": event.teams,
                "commence_time": event.commence_time
            }
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid opportunity ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching opportunity: {str(e)}")

@router.post("/{opportunity_id}/analyze", response_model=OpportunityAnalysisResponse)
async def analyze_opportunity(
    opportunity_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Trigger AI analysis for an opportunity"""
    try:
        opportunity_uuid = uuid.UUID(opportunity_id)
        
        # Check if opportunity exists
        stmt = select(ArbitrageOpportunity).where(ArbitrageOpportunity.id == opportunity_uuid)
        result = await db.execute(stmt)
        opportunity = result.scalar_one_or_none()
        
        if not opportunity:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        
        if opportunity.expires_at <= datetime.utcnow():
            raise HTTPException(status_code=400, detail="Opportunity has expired")
        
        # Trigger AI analysis in background
        background_tasks.add_task(ai_analyzer.analyze_opportunity, opportunity_id)
        
        return OpportunityAnalysisResponse(
            opportunity_id=opportunity_id,
            status="analysis_queued",
            message="AI analysis has been queued and will be completed shortly"
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid opportunity ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error queuing analysis: {str(e)}")

@router.get("/stats/summary")
async def get_opportunities_summary(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get summary statistics for arbitrage opportunities"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Total opportunities
        total_stmt = (
            select(func.count(ArbitrageOpportunity.id))
            .where(ArbitrageOpportunity.detected_at >= cutoff_date)
        )
        total_result = await db.execute(total_stmt)
        total_opportunities = total_result.scalar()
        
        # Active opportunities
        active_stmt = (
            select(func.count(ArbitrageOpportunity.id))
            .where(
                and_(
                    ArbitrageOpportunity.detected_at >= cutoff_date,
                    ArbitrageOpportunity.status.in_(["detected", "analyzed"]),
                    ArbitrageOpportunity.expires_at > datetime.utcnow()
                )
            )
        )
        active_result = await db.execute(active_stmt)
        active_opportunities = active_result.scalar()
        
        # Average profit
        avg_profit_stmt = (
            select(func.avg(ArbitrageOpportunity.profit_percentage))
            .where(ArbitrageOpportunity.detected_at >= cutoff_date)
        )
        avg_profit_result = await db.execute(avg_profit_stmt)
        avg_profit = avg_profit_result.scalar() or 0
        
        # Best opportunity
        best_stmt = (
            select(func.max(ArbitrageOpportunity.profit_percentage))
            .where(ArbitrageOpportunity.detected_at >= cutoff_date)
        )
        best_result = await db.execute(best_stmt)
        best_profit = best_result.scalar() or 0
        
        # Opportunities by sport
        sport_stmt = (
            select(Event.sport, func.count(ArbitrageOpportunity.id))
            .join(Event, ArbitrageOpportunity.event_id == Event.id)
            .where(ArbitrageOpportunity.detected_at >= cutoff_date)
            .group_by(Event.sport)
            .order_by(func.count(ArbitrageOpportunity.id).desc())
        )
        sport_result = await db.execute(sport_stmt)
        sport_breakdown = dict(sport_result.all())
        
        return {
            "period_days": days,
            "total_opportunities": total_opportunities,
            "active_opportunities": active_opportunities,
            "average_profit_percentage": round(float(avg_profit), 2),
            "best_profit_percentage": round(float(best_profit), 2),
            "sport_breakdown": sport_breakdown,
            "generated_at": datetime.utcnow()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")
