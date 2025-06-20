-- Initialize database with extensions and basic setup
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create indexes for better performance
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_sport_status ON events(sport, status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_commence_time ON events(commence_time);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_odds_event_bookmaker ON odds_snapshots(event_id, bookmaker);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_odds_captured_at ON odds_snapshots(captured_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_arb_profit_risk ON arbitrage_opportunities(profit_percentage, risk_score);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_arb_status_detected ON arbitrage_opportunities(status, detected_at);

-- Create materialized view for opportunity analytics
CREATE MATERIALIZED VIEW IF NOT EXISTS opportunity_analytics AS
SELECT 
    DATE_TRUNC('hour', detected_at) as hour,
    COUNT(*) as total_opportunities,
    AVG(profit_percentage) as avg_profit,
    MAX(profit_percentage) as max_profit,
    AVG(risk_score) as avg_risk,
    COUNT(CASE WHEN status = 'executed' THEN 1 END) as executed_count
FROM arbitrage_opportunities 
WHERE detected_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE_TRUNC('hour', detected_at)
ORDER BY hour DESC;

-- Create refresh function for materialized view
CREATE OR REPLACE FUNCTION refresh_opportunity_analytics()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW opportunity_analytics;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO arbitrage_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO arbitrage_user;
