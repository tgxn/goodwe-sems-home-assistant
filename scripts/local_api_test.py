#!/usr/bin/env python3
"""Local SEMS API wrapper for testing without Home Assistant."""
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))

from dotenv import load_dotenv
from sems.sems_api import SemsApi

# Load .env file
load_dotenv()

# Setup logging
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = log_dir / f"{timestamp}_local_test.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class MinimalHass:
    """Minimal Home Assistant stub for local testing."""

    async def async_add_executor_job(self, func, *args):
        """Execute function synchronously."""
        return func(*args)

def main():
    """Run the local API test."""
    logger.info("=" * 80)
    logger.info("SEMS Local API Wrapper - Starting")
    logger.info("=" * 80)

    # Load credentials from environment
    username = os.getenv("SEMS_USERNAME")
    password = os.getenv("SEMS_PASSWORD")

    if not username or not password:
        logger.error("SEMS_USERNAME and SEMS_PASSWORD must be set in .env file")
        sys.exit(1)

    logger.info(f"Loaded credentials for: {username}")

    # Initialize API with minimal HomeAssistant stub
    hass = MinimalHass()
    api = SemsApi(hass, username, password)

    # Test authentication
    logger.info("Testing authentication...")
    if not api.test_authentication():
        logger.error("Authentication failed")
        sys.exit(1)
    logger.info("✓ Authentication successful")

    # Fetch power station IDs
    logger.info("Fetching power station IDs...")
    power_stations = api.getPowerStationIds()
    logger.info(f"getPowerStationIds returned: {power_stations} (type: {type(power_stations).__name__})")
    
    # Save raw response
    if power_stations:
        with open(log_dir / f"{timestamp}_raw_getPowerStationIds.json", "w") as f:
            json.dump({"data": power_stations}, f, indent=2)
    
    # Handle both string and list returns
    if isinstance(power_stations, str) and power_stations:
        power_station_id = power_stations
        logger.info(f"Using power station ID (string): {power_station_id}")
    elif isinstance(power_stations, list) and len(power_stations) > 0:
        power_station_id = power_stations[0]
        logger.info(f"Using first power station ID (list): {power_station_id}")
    else:
        logger.error(f"No power station IDs returned or invalid format: {power_stations}")
        sys.exit(1)

    # Fetch monitoring data
    logger.info(f"Fetching data for power station {power_station_id}...")
    data = api.getData(power_station_id)
    if not data:
        logger.error("Failed to fetch monitoring data")
        sys.exit(1)
    logger.info("✓ Monitoring data retrieved successfully")

    # Save raw monitoring data
    with open(log_dir / f"{timestamp}_raw_monitoring_data.json", "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved raw data to {log_dir / f'{timestamp}_raw_monitoring_data.json'}")

    # Log summary
    logger.info("=" * 80)
    logger.info("API Call Summary:")
    logger.info(f"  - Power Station ID: {power_station_id}")
    logger.info(f"  - Inverters: {list(data.get('inverters', {}).keys()) if isinstance(data.get('inverters'), dict) else 'N/A'}")
    logger.info(f"  - Data keys: {list(data.keys())}")
    logger.info("=" * 80)
    logger.info("Test completed successfully")
    logger.info(f"All responses saved to logs/ directory with timestamp: {timestamp}")


if __name__ == "__main__":
    main()
