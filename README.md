# AI Web Signal Hunter

An end-to-end web intelligence prototype that crawls public web pages for a given niche, extracts structured market signals using Gemini or Groq, and ranks the strongest product/business opportunities with verifiable evidence.

## Architecture
1. **Discovery & Responsible Crawling (`src/crawler.py`)**: Queries DuckDuckGo for multi-domain URLs, validates `robots.txt` via `urllib.robotparser`, enforces crawl delays, extracts main text via `trafilatura`, and deduplicates content using MD5 hashing.
2. **Structured LLM Analysis (`src/analyzer.py`)**: Wraps untrusted web text in `<untrusted_web_content>` tags to prevent prompt injection and enforces strict Pydantic JSON schemas for signal categorization, scoring, and ≤30-word verbatim quotes.
3. **Transparent Opportunity Ranking (`src/ranker.py`)**: Groups signals by recurring theme and scores opportunities using:
   `Base = 0.40 * Relevance + 0.35 * Urgency + 0.25 * Confidence`
   `Multiplier = 1 + 0.15 * ln(Source_Count) + 0.10 * (Unique_Domains - 1)`
   `Opportunity Score = min(100, Base * Multiplier)`
4. **Storage & Dashboard (`src/database.py`, `app.py`)**: Persists runs in SQLite (`signals.db`) and renders an interactive Streamlit dashboard with CSV/JSON exports.

## Setup
1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt