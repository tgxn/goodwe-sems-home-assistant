# SEMS API Complete Data Mapping Analysis

## Raw API Response Structure

### Overview
The SEMS API `getData()` endpoint returns a comprehensive JSON object with the following main sections:

## 1. INFO Section (Station-level metadata)
Currently captured in `SemsData.info`:
- `powerstation_id` - Power station unique ID
- `stationname` - Station name  
- `capacity` - Total capacity (6.6 kW in example)
- `battery_capacity` - Battery capacity (16.6 kWh in example)
- `status` - Station status (1 = online)
- `has_pv` - Has PV array
- `has_statistics_charts` - Has charts data
- `time_span` - Timezone offset

**Action**: Already handled in coordinator data shaping.

---

## 2. KPI Section (Key Performance Indicators)
Available but may not be fully utilized:

| Field | Type | Unit | Current Status |
|-------|------|------|-----------------|
| `pac` | float | W | **NOT mapped** - could be "Grid Power" |
| `power` | float | W | **NOT mapped** - duplicate/similar to pac? |
| `month_generation` | float | kWh | **NOT mapped** - "Monthly Generation" |
| `day_income` | float | Currency | **MAPPED** as `iday` in inverter |
| `total_income` | float | Currency | **MAPPED** as `itotal` in inverter |
| `yield_rate` | float | ratio | **NOT mapped** - Performance/efficiency metric |
| `total_power` | float | kWh | **NOT mapped** - "Total Power Generated" |

**Action**: Should add `month_generation`, `yield_rate`, and clarify `pac` vs inverter `pac`.

---

## 3. INVERTER Array (Per-inverter detailed data)

### 3.1 Basic Info (Already Mapped)
```
✓ sn - Serial number
✓ name - Device name  
✓ type - Model type (e.g., "GW5K-EHA-G20")
✓ capacity - Rated power (kW)
✓ status - Status (1 = online, 0 = offline)
✓ is_stored - Is in database
✓ pac - Output power (W)
✓ etotal - Total energy generated (kWh)
✓ eday - Daily energy (kWh)
```

### 3.2 PV Array Inputs (Already Mapped)
```
✓ vpv1, vpv2, vpv3, vpv4 - PV string voltages (V)
✓ ipv1, ipv2, ipv3, ipv4 - PV string currents (A)
```

### 3.3 AC Grid Outputs (Already Mapped)
```
✓ vac1, vac2, vac3 - AC grid voltages (V)
✓ iac1, iac2, iac3 - AC grid currents (A)  
✓ fac1, fac2, fac3 - Grid frequencies (Hz)
```

### 3.4 Battery Management (Already Mapped)
```
✓ vbattery1, ibattery1 - Battery voltage/current
✓ soc - State of Charge (%)
✓ soh - State of Health (%)
✓ battery_count - Number of battery modules
✓ more_batterys[].* - Per-battery detailed data
  ✓ pbattery - Battery power (W)
  ✓ vbattery - Battery voltage (V)
  ✓ ibattery - Battery current (A)
  ✓ soc - State of charge (%)
  ✓ soh - State of health (%)
  ✓ bms_temperature - BMS temperature (°C)
  ✓ bms_charge_i_max - Max charge current (A)
  ✓ bms_discharge_i_max - Max discharge current (A)
```

### 3.5 Load/Backup Output (NOT MAPPED)
```
✗ vload - Backup output voltage (V)
✗ iload - Backup output current (A)
✗ pbackup - Backup output power (W)
```

**Action**: Add load/backup voltage, current, power sensors.

### 3.6 Grid Meter (Partially Mapped)
```
✓ pmeter - Grid meter power (W) - if exists
✗ buy - Grid import power (W)
✗ sell/seller - Grid export power (W)
✗ eTotalBuy - Total imported energy (kWh)
✗ eDayBuy - Daily imported energy (kWh)
```

**Action**: Add buy/sell grid energy tracking.

### 3.7 Battery Energy (Already Mapped)
```
✓ eChargeDay - Daily battery charge (kWh)
✓ eDischargeDay - Daily battery discharge (kWh)
✓ eBatteryCharge - Total battery charge (kWh)
✓ eBatteryDischarge - Total battery discharge (kWh)
```

### 3.8 Energy Statistics (NOT MAPPED) - IMPORTANT FOR HA ENERGY
```
✗ eTotalBuy - Total energy from grid (kWh)
✗ eDayBuy - Today's energy from grid (kWh)
✗ total_sell - Total sold to grid (kWh)
✗ total_buy - Total bought from grid (kWh)
✗ yesterday_buy_total - Yesterday's import
✗ yesterday_seller_total - Yesterday's export
```

**Action**: Critical for Home Assistant Energy dashboard.

### 3.9 Temperature & Other Diagnostics (Partially Mapped)
```
✓ tempperature - Inverter temperature (°C)
✓ firmwareversion - Firmware version
✓ bmssoftwareversion - BMS firmware version
✗ pv_power - Total PV power (W)
✗ reactive_power - Reactive power (VAR)
✗ pf - Power factor
```

### 3.10 invert_full Nested Object (Extensive Details)
This contains a full copy of inverter data with some additional fields:
```
✗ grid_conn_status - Grid connection status string
✗ micro_grid_flag - Has microgrid
✗ meterConnectStatus - Meter connection status
✗ mtActivepowerR, mtActivepowerS, mtActivepowerT - Per-phase meter power
```

**Action**: Some of this is redundant, but phase-specific power data could be useful.

---

## 4. POWERFLOW Section (Live Power Flow) - NOT MAPPED
Critical for real-time energy display:

```
✗ pv - PV output power ("0(W)" - formatted string)
✗ bettery - Battery power ("772.6(W)")
✗ load - Load power ("772.6(W)")
✗ grid - Grid power ("0(W)")
✗ soc - Battery state of charge (44)
✗ genset - Genset power (if available)
✗ pvStatus - PV connection status
✗ betteryStatus - Battery status (-1, 0, 1)
✗ gridStatus - Grid status (1 = connected)
```

**Action**: These are formatted strings but contain useful live data. Could parse and use.

---

## 5. ENERGY STATISTICS CHARTS (NOT MAPPED)
Important for Home Assistant Energy integration:

```
✗ energeStatisticsCharts.buy - Daily grid import
✗ energeStatisticsCharts.sell - Daily grid export
✗ energeStatisticsCharts.selfUseOfPv - PV self-consumption
✗ energeStatisticsCharts.charge - Battery charge today
✗ energeStatisticsCharts.disCharge - Battery discharge today
✗ energeStatisticsCharts.selfUseRate - % self-consumed
✗ energeStatisticsCharts.contributingRate - % grid contribution
```

**Action**: Critical for HA Energy dashboard. These are the daily statistics.

---

## 6. HOMEKIT/POWERFLOW Object (Live Dashboard Data)
Already partially mapped via powerflow sensors.

---

## Priority Actions for Complete HA Energy Support

### HIGH PRIORITY (Required for Energy Dashboard)
1. ✗ **Grid Buy/Sell Energy** - `eTotalBuy`, `total_sell` from inverter
2. ✗ **Daily Grid Buy/Sell** - `eDayBuy` from inverter  
3. ✗ **KPI: Monthly Generation** - `month_generation` from kpi
4. ✗ **Energy Statistics** - `energeStatisticsCharts` daily breakdown

### MEDIUM PRIORITY (Useful for Monitoring)
1. ✗ **Load Output** - `vload`, `iload`, `pbackup` (backup output)
2. ✗ **Grid Power Components** - Per-phase `mtActivepowerR/S/T`
3. ✗ **Power Factor** - `pf` from invert_full
4. ✗ **Battery Charge/Discharge Today** - separate from etotal
5. ✗ **Reactive Power** - `reactive_power`

### LOW PRIORITY (Diagnostics)
1. ✗ **Yield Rate** - Efficiency metric
2. ✗ **Grid Connection Status** - Text status string
3. ✗ **Microgrid Status** - If applicable

---

## Summary Statistics

| Category | Mapped | Total | Coverage |
|----------|--------|-------|----------|
| Inverter Basics | 8 | 8 | 100% |
| PV Inputs | 8 | 8 | 100% |
| AC Grid | 9 | 9 | 100% |
| Battery | 14 | 14 | 100% |
| Load/Backup | 0 | 3 | **0%** |
| Grid Meter | 1 | 5 | 20% |
| Battery Energy | 4 | 4 | 100% |
| Grid Buy/Sell | 0 | 4 | **0%** |
| KPI | 2 | 5 | 40% |
| Energy Charts | 0 | 7 | **0%** |
| **TOTAL** | **46** | **67** | **69%** |

---

## Recommendation

To achieve 100% coverage for Home Assistant Energy integration, prioritize:
1. Add grid buy/sell energy sensors (high impact)
2. Add daily energy statistics from energeStatisticsCharts
3. Add load/backup output sensors
4. Add grid meter buy/sell data
5. Add KPI monthly generation

This will enable full Energy Dashboard functionality.
