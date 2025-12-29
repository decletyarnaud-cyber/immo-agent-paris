# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Immo-Agent is a judicial real estate auction tracker for the Marseille, Aix-en-Provence, and Toulon regions (departments 13 and 83 in France). It scrapes auction listings, extracts data from legal documents (procès-verbaux), compares prices against official market data (DVF), and provides opportunity scoring.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# CLI commands (via main.py)
python main.py scrape          # Scrape auctions from all sources
python main.py analyze         # Analyze auctions against DVF market data
python main.py download-dvf    # Download DVF (Demandes de Valeurs Foncières) data
python main.py export          # Export auctions to CSV
python main.py web             # Start Streamlit web interface (localhost:8501)
python main.py run-all         # Full pipeline: scrape + analyze

# Scheduler for automated daily runs
python scheduler.py            # Run daemon (scrapes daily at 06:00)
python scheduler.py --once     # Single execution
python scheduler.py --run-now  # Execute immediately then continue as daemon
```

## Architecture

### Data Flow
```
Scrapers → Database (SQLite) → Analysis (DVF comparison) → Web UI / CSV Export
```

### Core Modules

**Scrapers** (`src/scrapers/`): Each scraper inherits from `BaseScraper` and implements site-specific parsing. Sources: Licitor, Enchères-Publiques, Vench, plus lawyer website scraper for PV documents.

**Extractors** (`src/extractors/`): PDF parsing with `pdfplumber`/`PyMuPDF`, OCR fallback via `pytesseract` for image-based PDFs. `PVDataExtractor` extracts structured data (address, surface, charges, occupation status).

**Analysis** (`src/analysis/`):
- `DVFClient` downloads and queries official French real estate transaction data
- `MarketAnalyzer` finds comparable sales and calculates market price/m²
- `PropertyValuator` computes opportunity scores (0-100) based on discount vs market

**Storage** (`src/storage/`):
- `Database` (SQLite) with `auctions` and `lawyers` tables
- `CSVHandler` for exports
- Core models: `Auction`, `Lawyer`, `DVFTransaction`

**Web** (`src/web/app.py`): Streamlit dashboard with search, filtering, opportunity badges, and CSV export.

### Key Data Models

`Auction`: Main entity with address, surface, mise_a_prix, date_vente, dates_visite, tribunal, lawyer_id, pv_status, score_opportunite, decote_pourcentage.

Opportunity scoring thresholds (in `config/settings.py`):
- Good deal: 20% below market
- Opportunity: 30% below market

### Configuration

All settings in `config/settings.py`: geographic scope (CITIES, DEPARTMENTS), source URLs, scraping delays, DVF endpoints, analysis thresholds.

Lawyer websites configured in `config/lawyers_config.yaml`.

## Language Note

This project uses French for domain terms (enchères, tribunal, avocat, mise à prix, procès-verbal). Code comments and variable names mix French domain terms with English programming conventions.
