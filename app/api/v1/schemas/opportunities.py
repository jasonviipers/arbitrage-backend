from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class EventInfo(BaseModel):
    sport: str
    teams: List[str]
    commence_time: datetime

class OpportunityBase(BaseModel):
    market_type: str
    profit_percentage: float = Field(..., ge=0)
    expected_profit: float = Field(..., ge=0)
    total_stake: float = Field(..., ge=0)
    risk_score: float = Field(..., ge=1, le=10)
    bookmaker_stakes: Dict[str, Dict[str, float]]
    bookmaker_odds: Dict[str, Dict[str, float]]

class OpportunityResponse(OpportunityBase):
    id: str
    event_id: str
    ai_score: Optional[float] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    status: str
    detected_at: datetime
    expires_at: Optional[datetime] = None
    event: EventInfo

class OpportunityListItem(BaseModel):
    id: str
    event_id: str
    market_type: str
    profit_percentage: float
    expected_profit: float
    total_stake: float
    risk_score: float
    ai_score: Optional[float] = None
    status: str
    detected_at: datetime
    expires_at: Optional[datetime] = None
    bookmaker_stakes: Dict[str, Dict[str, float]]
    bookmaker_odds: Dict[str, Dict[str, float]]
    event: EventInfo

class OpportunityListResponse(BaseModel):
    opportunities: List[OpportunityListItem]
    total: int
    skip: int
    limit: int

class OpportunityAnalysisRequest(BaseModel):
    force_reanalysis: bool = False

class OpportunityAnalysisResponse(BaseModel):
    opportunity_id: str
    status: str
    message: str
    analysis: Optional[Dict[str, Any]] = None
