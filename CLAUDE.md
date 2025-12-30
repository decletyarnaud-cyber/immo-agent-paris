# CLAUDE.md - Immo Agent Paris

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## Project Overview

Immo-Agent Paris is a judicial real estate auction tracker for Paris and the Île-de-France region (departments 75, 77, 78, 91, 92, 93, 94, 95). It scrapes auction listings from multiple sources, extracts data from legal documents (procès-verbaux), compares prices against official market data (DVF), and provides opportunity scoring.

## Service Info

| Property | Value |
|----------|-------|
| **Service Name** | immo-paris |
| **Port** | 8502 |
| **Type** | Streamlit |
| **URL** | http://localhost:8502 |
| **GitHub** | https://github.com/decletyarnaud-cyber/immo-agent-paris |
| **launchd** | `com.ade.immo-paris` |

### Service Management

```bash
# Via pctl (recommended)
pctl start immo-paris
pctl stop immo-paris
pctl restart immo-paris
pctl logs immo-paris
pctl open immo-paris

# Direct launchctl
launchctl load ~/Library/LaunchAgents/com.ade.immo-paris.plist
launchctl unload ~/Library/LaunchAgents/com.ade.immo-paris.plist
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# CLI commands (via main.py)
python main.py scrape          # Scrape auctions from all sources
python main.py analyze         # Analyze auctions against DVF market data
python main.py download-dvf    # Download DVF (Demandes de Valeurs Foncières) data
python main.py export          # Export auctions to CSV
python main.py web             # Start Streamlit web interface (localhost:8502)
python main.py run-all         # Full pipeline: scrape + analyze

# Scheduler for automated daily runs
python scheduler.py            # Run daemon (scrapes daily at 06:00)
python scheduler.py --once     # Single execution
python scheduler.py --run-now  # Execute immediately then continue as daemon

# Direct Streamlit start
streamlit run src/web/app.py --server.port 8502
```

## Architecture

### Data Flow

```
Scrapers → Database (SQLite) → Analysis (DVF comparison) → Web UI / CSV Export
```

### Core Modules

**Scrapers** (`src/scrapers/`):
- `LicitorScraper`: Scrapes licitor.com tribunal listings
- `EncherePubliquesScraper`: Scrapes encheres-publiques.com
- `VenchScraper`: Scrapes vench.fr
- `LawyerScraper`: Extracts PV documents from lawyer websites
- `BaseScraper`: Abstract base class for all scrapers

**Extractors** (`src/extractors/`):
- `PDFParser`: PDF text extraction with pdfplumber/PyMuPDF
- `OCRHandler`: Fallback OCR via pytesseract for image PDFs
- `DataExtractor`: Structured data extraction from PV documents
- `LLMExtractor`: Claude-powered extraction for complex documents

**Analysis** (`src/analysis/`):
- `DVFClient`: Downloads/queries official French transaction data
- `MarketAnalyzer`: Finds comparable sales, calculates €/m²
- `PropertyValuator`: Computes opportunity scores (0-100)
- `NeighborhoodAnalyzer`: Analyzes area characteristics
- `MultiSourceAnalyzer`: Aggregates data from multiple sources

**Storage** (`src/storage/`):
- `Database`: SQLite with auctions, lawyers tables
- `CSVHandler`: CSV export functionality
- Models: `Auction`, `Lawyer`, `DVFTransaction`

**Web** (`src/web/app.py`):
- Streamlit dashboard
- Search and filtering by arrondissement
- Opportunity badges
- Map visualization (Folium)
- CSV export

### Key Data Models

**Auction**:
- `address`, `surface`, `mise_a_prix`
- `date_vente`, `dates_visite`
- `tribunal`, `lawyer_id`
- `pv_status`, `pv_url`
- `score_opportunite`, `decote_pourcentage`
- `prix_m2_marche`, `prix_m2_vente`
- `arrondissement` (for Paris)

### Opportunity Scoring

Thresholds in `config/settings.py`:
- **Good deal**: 20%+ below market
- **Opportunity**: 30%+ below market
- **Excellent**: 40%+ below market

## Data Sources

1. **Licitor** (licitor.com) - Tribunal auction listings
2. **Enchères-Publiques** (encheres-publiques.com) - Aggregator
3. **Vench** (vench.fr) - Additional source
4. **DVF** (data.gouv.fr) - Official transaction data
5. **Lawyer websites** - PV documents

## Configuration

### config/settings.py

```python
DEPARTMENTS = ["75", "77", "78", "91", "92", "93", "94", "95"]  # Île-de-France
CITIES = ["Paris", "Versailles", "Nanterre", "Bobigny", "Créteil", ...]
TRIBUNAUX = ["TJ Paris", "TJ Versailles", "TJ Nanterre", ...]
```

### config/lawyers_config.yaml

Lawyer website configurations for PV document scraping.

## Database

SQLite database at `data/auctions.db`:

```sql
-- Main tables
auctions (id, address, surface, mise_a_prix, date_vente, ...)
lawyers (id, name, email, phone, tribunal, website)
dvf_transactions (id, address, price, surface, date, ...)
```

## Deployment

This project is configured for Railway deployment:
- `Procfile`: Defines web process
- `railway.json`: Railway configuration
- `.streamlit/config.toml`: Streamlit settings

## Language Note

This project uses French domain terms:
- **enchères** = auctions
- **tribunal** = court
- **avocat** = lawyer
- **mise à prix** = starting price
- **procès-verbal (PV)** = auction report/minutes
- **adjudication** = sale/award
- **arrondissement** = district (Paris)
