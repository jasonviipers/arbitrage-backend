from sqlalchemy import Column, String, DateTime, JSON, Float, Integer, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

class Event(Base):
    __tablename__ = "events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id = Column(String, unique=True, nullable=False, index=True)
    sport = Column(String, nullable=False, index=True)
    teams = Column(JSON, nullable=False)
    commence_time = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String, default="upcoming", index=True)
    metadata = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('ix_events_sport_status', 'sport', 'status'),
        Index('ix_events_commence_time', 'commence_time'),
    )

class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    bookmaker = Column(String, nullable=False, index=True)
    market_type = Column(String, nullable=False, default="h2h")
    odds_data = Column(JSON, nullable=False)
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    is_active = Column(Boolean, default=True, index=True)
    
    __table_args__ = (
        Index('ix_odds_event_bookmaker', 'event_id', 'bookmaker'),
        Index('ix_odds_captured_at', 'captured_at'),
        Index('ix_odds_active_recent', 'is_active', 'captured_at'),
    )

class ArbitrageOpportunity(Base):
    __tablename__ = "arbitrage_opportunities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    market_type = Column(String, nullable=False)
    profit_percentage = Column(Float, nullable=False, index=True)
    total_stake = Column(Float, nullable=False)
    bookmaker_stakes = Column(JSON, nullable=False)  # {bookmaker: {outcome: stake}}
    bookmaker_odds = Column(JSON, nullable=False)    # {bookmaker: {outcome: odds}}
    expected_profit = Column(Float, nullable=False)
    risk_score = Column(Float, default=0.0, index=True)
    ai_score = Column(Float, nullable=True, index=True)
    ai_analysis = Column(JSON, nullable=True)
    status = Column(String, default="detected", index=True)  # detected, analyzed, executed, expired
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index('ix_arb_profit_risk', 'profit_percentage', 'risk_score'),
        Index('ix_arb_status_detected', 'status', 'detected_at'),
        Index('ix_arb_active', 'status', 'expires_at'),
    )

class Portfolio(Base):
    __tablename__ = "portfolio"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    total_bankroll = Column(Float, nullable=False)
    available_balance = Column(Float, nullable=False)
    allocated_balance = Column(Float, default=0.0)
    total_profit = Column(Float, default=0.0)
    total_bets = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    bookmaker_balances = Column(JSON, default=dict)  # {bookmaker: balance}
    risk_settings = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class BookmakerStatus(Base):
    __tablename__ = "bookmaker_status"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bookmaker = Column(String, nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True, index=True)
    reliability_score = Column(Float, default=5.0)  # 1-10 scale
    api_status = Column(String, default="unknown")  # healthy, degraded, down
    last_successful_fetch = Column(DateTime(timezone=True), nullable=True)
    error_count = Column(Integer, default=0)
    rate_limit_reset = Column(DateTime(timezone=True), nullable=True)
    metadata = Column(JSON, default=dict)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    permissions = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())