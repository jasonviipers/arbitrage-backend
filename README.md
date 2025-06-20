# Sports Betting Arbitrage API

## Overview

This backend system is designed to detect and manage arbitrage opportunities in sports betting markets. It automatically collects odds from various bookmakers, identifies profitable arbitrage opportunities, and provides tools for analysis and execution.

## Features

- **Real-time Odds Collection**: Automatically fetches odds from multiple bookmakers
- **Arbitrage Detection**: Identifies profitable arbitrage opportunities across different markets
- **Risk Analysis**: Evaluates and scores opportunities based on risk factors
- **AI-Powered Analysis**: Uses OpenAI's GPT-4 to analyze opportunities
- **Portfolio Management**: Tracks bankroll, stakes, and profits
- **RESTful API**: Comprehensive API for integration with frontend applications
- **Authentication & Authorization**: Secure JWT-based authentication system
- **Rate Limiting**: Protects API from abuse

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Caching**: Redis
- **Authentication**: JWT
- **Containerization**: Docker & Docker Compose
- **AI Integration**: OpenAI API

## Prerequisites

- Docker and Docker Compose
- API keys for:
  - The Odds API
  - OpenAI API
  - (Optional) Betfair API
  - (Optional) Smarkets API

## Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd arbitrage-backend
```

2. Create a `.env` file based on the provided example:

```bash
cp .env.example .env
```

3. Edit the `.env` file and add your API keys and other configuration options.

4. Start the application using Docker Compose:

```bash
docker-compose up -d
```

## API Documentation

When running in development mode, API documentation is available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

The API is organized into the following groups:

- `/api/v1/auth`: Authentication endpoints
- `/api/v1/events`: Sports events data
- `/api/v1/opportunities`: Arbitrage opportunities
- `/api/v1/portfolio`: User portfolio management
- `/api/v1/bookmakers`: Bookmaker status and information
- `/api/v1/health`: System health checks

## Environment Variables

Key configuration options in the `.env` file:

```
# Environment
ENVIRONMENT=development
DEBUG=true

# Database
DATABASE_URL=postgresql+asyncpg://arbitrage_user:arbitrage_pass@localhost:5432/arbitrage_db
REDIS_URL=redis://localhost:6379

# External APIs
ODDS_API_KEY=your_odds_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Security
JWT_SECRET_KEY=your_super_secret_jwt_key_here_make_it_long_and_random

# Business Logic
MIN_ARBITRAGE_PERCENTAGE=2.0
MAX_STAKE_PERCENTAGE=10.0
DEFAULT_BANKROLL=10000.0
```

## Development

For local development without Docker:

1. Set up a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the application:

```bash
uvicorn app.main:app --reload
```