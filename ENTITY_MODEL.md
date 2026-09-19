# SEMS AU Entity Model

This integration models the AU API as a single station feed. Home Assistant gets one device per station, and all inverter, battery-control, powerflow, REST, and MQTT values attach to that device.

## Real runtime model

The coordinator normalizes the SEMS response into:

- `SemsData.station`: station-level capacity, KPI, income, yield, and environmental values
- `SemsData.inverters`: keyed by inverter serial number
- `SemsData.powerflow`: station-level AC flow metrics (`pv`, `load`, `grid`, `battery`, `genset`, `soc`, plus chart/totals when present)
- `SemsData.batteries`: battery cabinet metadata and supported functions
- `SemsData.immediate_charging`: control metadata for battery charging features

REST values and MQTT values are normalized into the same coordinator fields so sensors do not need source-specific parsing.

## Which data source drives which entities

### Station entities

These are built from `data.station` and describe the site as a whole.

Examples:

- Station Status
- Station Rated Solar Capacity
- Station Rated Battery Capacity
- Station Current Output Power
- Station Energy This Month
- Station Lifetime Solar Energy
- Station Yield Rate
- Station Income Today / Station Income Total
- CO2 Avoided
- Coal Saved
- Trees Equivalent

### Inverter entities

These are built from `data.inverters[serial_number]` and attached to the station device. The inverter serial number remains in the unique ID only to disambiguate per-inverter data.

Examples:

- status
- rated AC capacity
- current AC output power
- lifetime energy
- temperature
- PV string voltage/current
- grid voltage/current/frequency
- battery voltage/current
- backup output voltage/current/power
- battery state of charge / state of health
- inverter power factor / reactive power / leakage current
- grid import/export energy
- battery charge/discharge totals
- backup output energy
- generator power/energy
- daily / monthly / total inverter energy values

Each inverter entity uses a station-prefixed unique ID: `{station_id}-{inverter_serial}-{field}`.

### Powerflow entities

These are built from the station-level powerflow hash in `data.powerflow`.

Examples:

- Current Home Load Power
- Current Solar Generation Power
- Current Grid Import Export Power
- Current Battery Charge Discharge Power
- Current Generator Power
- Battery State of Charge
- Grid Import Today / Grid Export Today
- Daily and total battery / self-use / load-consumption data

The values are normalized from REST payload keys such as:

- `powerflow.pv`
- `powerflow.load`
- `powerflow.grid`
- `powerflow.bettery` -> `powerflow.battery`
- `powerflow.genset`
- `powerflow.soc`
- `powerflow.Charts_*`
- `powerflow.Totals_*`

The live MQTT listener updates the same station powerflow fields from the station topic. MQTT kW values are converted to W before they reach entities.

Signed flow values use the direction/status field supplied by SEMS. For example, grid power is exposed as a signed import/export value and battery power is exposed as a signed charge/discharge value.

MQTT mapping:

- `pSystem` -> `powerflow.pv` and `powerflow.system_power` in W
- `pConsum` -> `powerflow.load` in W
- `pGrid` -> `powerflow.grid` in W
- `pBat` -> `powerflow.battery` in W
- `pAc` -> `powerflow.ac_power` in W
- `pDc` -> `powerflow.dc_power` in W
- `qAc` -> `powerflow.reactive_power` in var
- `fAc` -> `powerflow.grid_frequency` in Hz
- `pf` -> `powerflow.power_factor`
- `soc` -> `powerflow.soc` in percent

The MQTT `stationId`, `time`, `traceId`, and `flows` fields are retained in the coordinator update for debugging/source context, but they are not currently exposed as Home Assistant sensors. They are identifiers, timestamps, or graph metadata rather than user-facing measurements.

## Device topology

The effective topology is:

- One config entry per station
- One Home Assistant device per station
- All inverter sensors, powerflow sensors, switches, and number controls attach to that station device

This matches the real AU SEMS response: a station/home feed with nested inverter and powerflow data.

## Intentionally Unmapped API Fields

The integration does not expose every raw API field as a sensor. The remaining raw fields are mostly one of:

- account/contact/location metadata (`owner_*`, address, organization IDs)
- opaque IDs and relation IDs
- image URLs and weather forecast blobs
- raw dashboard layout/equipment descriptors
- duplicated display strings when a numeric field already exists
- internal feature flags and unsupported equipment flags

Those can be added later if they become useful, but they are not currently better HA entities than the normalized numeric station, inverter, and powerflow measurements.
