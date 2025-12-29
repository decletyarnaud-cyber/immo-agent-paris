#!/usr/bin/env python3
"""
Scheduler for automated daily scraping and analysis
"""
import time
import sys
from datetime import datetime
from pathlib import Path
from loguru import logger

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/scheduler_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG"
)

try:
    import schedule
except ImportError:
    logger.error("Please install 'schedule' package: pip install schedule")
    sys.exit(1)

from main import run_scraping, run_analysis, download_dvf, export_csv


def daily_job():
    """Run the full daily pipeline"""
    logger.info("=" * 50)
    logger.info(f"Starting daily job at {datetime.now()}")
    logger.info("=" * 50)

    try:
        # Step 1: Scrape all sources
        logger.info("Step 1: Scraping auction sources...")
        run_scraping()

        # Step 2: Analyze against market data
        logger.info("Step 2: Analyzing auctions...")
        run_analysis()

        # Step 3: Export to CSV
        logger.info("Step 3: Exporting to CSV...")
        export_csv()

        logger.info("Daily job completed successfully")

    except Exception as e:
        logger.error(f"Daily job failed: {e}")


def weekly_dvf_update():
    """Download fresh DVF data weekly"""
    logger.info("Weekly DVF update...")
    try:
        download_dvf()
        logger.info("DVF update completed")
    except Exception as e:
        logger.error(f"DVF update failed: {e}")


def run_scheduler(run_now: bool = False):
    """
    Run the scheduler

    Args:
        run_now: If True, run the daily job immediately before starting schedule
    """
    logger.info("Starting Immo-Agent Scheduler")
    logger.info("Scheduled jobs:")
    logger.info("  - Daily scraping & analysis: 06:00")
    logger.info("  - Weekly DVF update: Sunday 03:00")

    # Schedule daily job at 6 AM
    schedule.every().day.at("06:00").do(daily_job)

    # Schedule weekly DVF update on Sunday at 3 AM
    schedule.every().sunday.at("03:00").do(weekly_dvf_update)

    # Run immediately if requested
    if run_now:
        logger.info("Running initial job...")
        daily_job()

    # Run the scheduler loop
    logger.info("Scheduler is running. Press Ctrl+C to stop.")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Immo-Agent Scheduler for automated scraping"
    )

    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run the daily job immediately before starting schedule"
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Run the daily job once and exit"
    )

    args = parser.parse_args()

    if args.once:
        daily_job()
    else:
        run_scheduler(run_now=args.run_now)


if __name__ == "__main__":
    main()
