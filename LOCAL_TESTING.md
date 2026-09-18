# Local SEMS API Testing

This directory contains a simple wrapper script to test the SEMS API without running Home Assistant.

## Setup

1. Create a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements-local.txt
   ```

3. Create a `.env` file with your SEMS credentials:
   ```bash
   cp .env.example .env
   # Edit .env and add your SEMS_USERNAME and SEMS_PASSWORD
   ```

4. Run the test script:
   ```bash
   python scripts/local_api_test.py
   ```

## What It Does

- Tests authentication with the SEMS API
- Fetches power station IDs (or uses the one from .env)
- Retrieves monitoring data for the power station
- Logs all activity to `logs/{timestamp}_local_test.log`
- Saves **unfiltered raw API responses** to JSON files in `logs/` for inspection
- Displays summary of captured data

## Output Files

All data is logged to the `logs/` directory:

| File | Purpose |
|------|---------|
| `{timestamp}_local_test.log` | Complete debug log of test run |
| `{timestamp}_raw_getPowerStationIds.json` | Raw power station list response |
| `{timestamp}_raw_monitoring_data.json` | **Complete API response** - 1300+ lines of detailed data |

## Analyzing the API Response

After running the test, use the analysis documents to understand available data:

1. **[SEMS_DATA_ANALYSIS_SUMMARY.md](../SEMS_DATA_ANALYSIS_SUMMARY.md)** - Quick overview of data coverage (69% mapped)
2. **[SEMS_API_DATA_MAPPING.md](../SEMS_API_DATA_MAPPING.md)** - Complete breakdown of all 67 available data points
3. **[MISSING_SENSORS_IMPLEMENTATION.md](../MISSING_SENSORS_IMPLEMENTATION.md)** - Exact code to add missing sensors

## What Data You Get

A single `getData()` call returns comprehensive system data:

```
✓ Inverter details (status, power, efficiency, temperature)
✓ PV array data (4 strings × voltage + current each)
✓ AC grid data (3 phases × voltage + current + frequency)
✓ Battery data (voltage, current, SOC, SOH, BMS info)
✓ Energy counters (daily, monthly, total - generation, import, export)
✓ Load/backup output details
✓ Weather forecast
✓ Live power flow (PV → Battery → Grid → Load)
✓ Energy statistics and efficiency metrics
```

**Coverage**: Currently 46/67 key metrics are mapped (69%).

## Data Quality

- ✓ All energy values are cumulative (suitable for Home Assistant TOTAL_INCREASING)
- ✓ All power values update in real-time (suitable for MEASUREMENT)
- ✓ Per-string and per-phase granularity available
- ✓ Multiple battery modules supported
- ✓ Data is timestamped and validated

## Example Commands

### Test authentication only
```bash
# The script automatically tests auth first
python scripts/local_api_test.py
```

### Inspect raw response
```bash
# After running the script, view the complete API response
cat logs/20260918_170730_raw_monitoring_data.json | jq '.inverter[0]'
```

### Check available data paths
```bash
# Use jq to explore the API structure
cat logs/20260918_170730_raw_monitoring_data.json | jq 'keys'
```

## Implementation Guide for Missing Data

To add support for grid buy/sell energy and other missing sensors:

1. Open `custom_components/sems/sensor.py`
2. Follow examples in [MISSING_SENSORS_IMPLEMENTATION.md](../MISSING_SENSORS_IMPLEMENTATION.md)
3. Use `{timestamp}_raw_monitoring_data.json` to verify JSON paths
4. Test with Home Assistant after adding sensors

## Notes

- The script uses minimal mocking of the Home Assistant environment (only what's needed)
- All logging is sent to both console and the log file
- The wrapper preserves all the original API logic and error handling from `sems_api.py`
- Raw JSON responses are saved unfiltered for analysis
- Sensitive data (email, serial numbers) is logged but marked for redaction

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "SEMS_USERNAME and SEMS_PASSWORD must be set" | Create `.env` file from `.env.example` and add credentials |
| "Authentication failed" | Check credentials are correct in `.env` |
| "Failed to fetch power station IDs" | Account may not have any power stations configured |
| "Failed to fetch monitoring data" | Power station ID may be incorrect or offline |

