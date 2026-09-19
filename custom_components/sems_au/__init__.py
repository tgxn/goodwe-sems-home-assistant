"""The sems integration."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_REGION,
    CONF_STATION_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SEMS_REGION,
    DOMAIN,
    GOODWE_SPELLING,
    PLATFORMS,
    redact_for_log,
)
from .sems_api import SemsApi, SemsRateLimitedError
from .sems_mqtt import SemsMqttListener

_LOGGER: logging.Logger = logging.getLogger(__package__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_IMMEDIATE_CHARGING_FUNCTION_KEYS = {
    "immediate_charge",
    "stop_charging",
    "end_charge_soc",
    "bat_immediate_charge_power",
}

_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _decimal_value(value: Any) -> Decimal | None:
    """Return a Decimal from SEMS numeric strings, including values with units."""

    if value in (None, ""):
        return None
    if isinstance(value, str):
        match = _NUMBER_PATTERN.search(value)
        if match is None:
            return None
        value = match.group(0)
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int_value(value: Any) -> int | None:
    """Return an int for SEMS status values."""

    decimal_value = _decimal_value(value)
    if decimal_value is None:
        return None
    return int(decimal_value)


def _set_if_not_none(data: dict[str, Any], key: str, value: Any) -> None:
    """Set a key only when SEMS supplied a usable value."""

    if value is not None:
        data[key] = value


def _normalize_rest_powerflow(
    data_result: dict[str, Any], kpi: dict[str, Any]
) -> dict[str, Any] | None:
    """Normalize REST powerflow data to the station powerflow model."""

    if not data_result.get("hasPowerflow"):
        return None

    raw_powerflow = data_result.get("powerflow")
    if not isinstance(raw_powerflow, dict):
        raw_powerflow = {}

    powerflow: dict[str, Any] = {"source": "rest"}
    for source_key, target_key in (
        ("pv", "pv"),
        ("load", "load"),
        ("grid", "grid"),
        (GOODWE_SPELLING.battery, "battery"),
        ("genset", "genset"),
    ):
        _set_if_not_none(
            powerflow, target_key, _decimal_value(raw_powerflow.get(source_key))
        )

    for source_key, target_key in (
        ("pvStatus", "pvStatus"),
        ("loadStatus", "loadStatus"),
        ("gridStatus", "gridStatus"),
        (GOODWE_SPELLING.batteryStatus, "batteryStatus"),
    ):
        _set_if_not_none(
            powerflow, target_key, _int_value(raw_powerflow.get(source_key))
        )

    _set_if_not_none(powerflow, "soc", _decimal_value(raw_powerflow.get("soc")))
    _set_if_not_none(
        powerflow, "all_time_generation", _decimal_value(kpi.get("total_power"))
    )

    has_energy_statistics_charts = bool(
        data_result.get(GOODWE_SPELLING.hasEnergyStatisticsCharts)
    )
    powerflow[GOODWE_SPELLING.hasEnergyStatisticsCharts] = has_energy_statistics_charts

    if has_energy_statistics_charts:
        charts = data_result.get(GOODWE_SPELLING.energyStatisticsCharts)
        if not isinstance(charts, dict):
            charts = {}
        totals = data_result.get(GOODWE_SPELLING.energyStatisticsTotals)
        if not isinstance(totals, dict):
            totals = {}

        for key, value in charts.items():
            _set_if_not_none(powerflow, f"Charts_{key}", _decimal_value(value))
        for key, value in totals.items():
            _set_if_not_none(powerflow, f"Totals_{key}", _decimal_value(value))

    return powerflow


def _normalize_station_data(
    data_result: dict[str, Any], kpi: dict[str, Any]
) -> dict[str, Any]:
    """Normalize station-level REST values."""

    station: dict[str, Any] = {}
    info = data_result.get("info")
    if not isinstance(info, dict):
        info = {}

    for source_key, target_key in (
        ("capacity", "rated_solar_capacity"),
        ("battery_capacity", "rated_battery_capacity"),
        ("longitude", "longitude"),
        ("latitude", "latitude"),
        ("time_span", "timezone_offset"),
    ):
        _set_if_not_none(station, target_key, _decimal_value(info.get(source_key)))

    _set_if_not_none(station, "status", _int_value(info.get("status")))

    for source_key, target_key in (
        ("month_generation", "energy_this_month"),
        ("pac", "current_output_power"),
        ("total_power", "lifetime_solar_energy"),
        ("day_income", "income_today"),
        ("total_income", "income_total"),
        ("yield_rate", "yield_rate"),
    ):
        _set_if_not_none(station, target_key, _decimal_value(kpi.get(source_key)))

    environmental = data_result.get("hjgx")
    if isinstance(environmental, dict):
        for source_key, target_key in (
            ("co2", "co2_avoided"),
            ("tree", "trees_equivalent"),
            ("coal", "coal_saved"),
        ):
            _set_if_not_none(
                station, target_key, _decimal_value(environmental.get(source_key))
            )

    return station


@dataclass(slots=True)
class SemsRuntimeData:
    """Runtime data stored on the config entry."""

    api: SemsApi
    coordinator: SemsDataUpdateCoordinator
    mqtt_listener: SemsMqttListener
    mqtt_task: asyncio.Task[None]


type SemsConfigEntry = ConfigEntry[SemsRuntimeData]


@dataclass(slots=True)
class SemsData:
    """Runtime SEMS data returned by the coordinator."""

    inverters: dict[str, dict[str, Any]]
    station: dict[str, Any] | None = None
    batteries: dict[str, dict[str, dict[str, Any]]] | None = None
    immediate_charging: dict[str, dict[str, Any]] | None = None
    powerflow: dict[str, Any] | None = None
    currency: str | None = None
    station_id: str | None = None
    station_name: str | None = None


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the sems component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SemsConfigEntry) -> bool:
    """Set up sems from a config entry."""
    region = entry.data.get(CONF_REGION, DEFAULT_SEMS_REGION)
    sems_api = SemsApi(
        hass, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], region
    )
    coordinator = SemsDataUpdateCoordinator(hass, sems_api, entry)
    await coordinator.async_config_entry_first_refresh()

    mqtt_listener = SemsMqttListener(
        hass,
        sems_api,
        entry.data[CONF_STATION_ID],
        region,
        coordinator.async_apply_mqtt_powerflow_update,
    )
    mqtt_task = hass.async_create_background_task(
        mqtt_listener.async_run(), f"{DOMAIN} live data listener"
    )
    entry.runtime_data = SemsRuntimeData(
        api=sems_api,
        coordinator=coordinator,
        mqtt_listener=mqtt_listener,
        mqtt_task=mqtt_task,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    if entry.version > 3:
        _LOGGER.error("Cannot migrate entry version %s", entry.version)
        return False

    data = dict(entry.data)
    if entry.version < 2:
        station_id = entry.data.get(CONF_STATION_ID)
        if entry.unique_id is None and isinstance(station_id, str) and station_id:
            hass.config_entries.async_update_entry(entry, unique_id=station_id)

    if entry.version < 3:
        data.setdefault(CONF_REGION, DEFAULT_SEMS_REGION)
        hass.config_entries.async_update_entry(entry, data=data, version=3)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SemsConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    entry.runtime_data.mqtt_listener.stop()
    entry.runtime_data.mqtt_task.cancel()
    try:
        await asyncio.gather(entry.runtime_data.mqtt_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    return True


class SemsDataUpdateCoordinator(DataUpdateCoordinator[SemsData]):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, sems_api: SemsApi, entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self.sems_api = sems_api
        self.station_id = entry.data[CONF_STATION_ID]

        update_interval = timedelta(
            seconds=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_get_energy_storage_cabinets(
        self, data_result: dict[str, Any]
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch the energy storage cabinets when batteries are available."""
        if not data_result.get("info", {}).get("is_stored", False):
            return {}

        _LOGGER.debug("Getting energy storage integrated cabinets")
        cabinets: dict[str, list[dict[str, Any]]] = {}
        for inverter in data_result.get("inverter", {}):
            sn = inverter.get("invert_full", {}).get("sn")
            if not sn:
                continue
            try:
                result = await self.hass.async_add_executor_job(
                    self.sems_api.getEnergyStorageIntegratedCabinets,
                    self.station_id,
                    sn,
                )
                cabinets[sn] = result if isinstance(result, list) else []
            except Exception as err:
                _LOGGER.debug(
                    "Unable to fetch energy storage cabinets for %s: %s",
                    redact_for_log(sn),
                    err,
                )
                cabinets[sn] = []
        return cabinets

    async def _async_get_battery_functions(
        self, energy_storage_cabinets: dict[str, list[dict[str, Any]]]
    ) -> dict[str, dict[str, dict[str, Any]]] | None:
        """Fetch and retain supported battery functions."""
        if energy_storage_cabinets:
            _LOGGER.debug("Getting battery general functions for each cabinet")
        battery_general_functions: dict[str, dict[str, dict[str, Any]]] = {}
        for sn, bats in energy_storage_cabinets.items():
            battery_general_functions[sn] = {}
            for bat in bats:
                if not isinstance(bat, dict) or not isinstance(
                    bat.get("translateCode"), str
                ):
                    continue
                bat_code = bat["translateCode"]
                try:
                    result = await self.hass.async_add_executor_job(
                        self.sems_api.getBatteryGeneralFunctions, sn, bat.get("no", 0)
                    )
                    battery_general_functions[sn][bat_code] = result
                except Exception as err:
                    _LOGGER.debug(
                        "Unable to fetch battery functions for %s (battery %s): %s",
                        redact_for_log(sn),
                        bat_code,
                        err,
                    )
                    battery_general_functions[sn][bat_code] = {}

        batteries: dict[str, dict[str, dict[str, Any]]] = {}
        for sn, bats in battery_general_functions.items():
            for bat_id, bat in bats.items():
                if not isinstance(bat_id, str):
                    continue
                for child in bat.get("functionMenus", {}).get("children", []):
                    for func in child.get("functions", []):
                        function_key = func.get("translateKey")
                        if not isinstance(function_key, str):
                            continue
                        if function_key not in _IMMEDIATE_CHARGING_FUNCTION_KEYS:
                            continue

                        if sn not in batteries:
                            batteries[sn] = {}
                        if bat_id not in batteries[sn]:
                            batteries[sn][bat_id] = {
                                "name": next(
                                    (
                                        cabinet.get("name", "")
                                        for cabinet in energy_storage_cabinets.get(
                                            sn, []
                                        )
                                        if cabinet.get("translateCode") == bat_id
                                    ),
                                    "",
                                ),
                                "functions": {},
                            }

                        batteries[sn][bat_id]["functions"][function_key] = {
                            "address": func.get("address"),
                            "id": func.get("id"),
                        }

        return batteries or None

    async def _async_get_immediate_charging(
        self, batteries: dict[str, dict[str, dict[str, Any]]] | None
    ) -> dict[str, dict[str, Any]] | None:
        """Fetch immediate-charging state for battery-equipped inverters."""
        if not batteries:
            return None

        immediate_charging: dict[str, dict[str, Any]] = {}
        for inverter_sn in batteries:
            try:
                immediate_charging_result = await self.hass.async_add_executor_job(
                    self.sems_api.getBatteryImmediateChargingStates, inverter_sn
                )
                state_data = (immediate_charging_result or {}).get("data", {})
                immediate_charging[inverter_sn] = {
                    "enabled": bool(state_data.get("47545", 0)),
                    "end_charge_soc": state_data.get("47546", 0),
                    "charging_power": state_data.get("47603", 0),
                }
            except Exception as err:
                _LOGGER.debug(
                    "Unable to fetch immediate charging state for %s: %s",
                    redact_for_log(inverter_sn),
                    err,
                )
                immediate_charging[inverter_sn] = {
                    "enabled": False,
                    "end_charge_soc": 0,
                    "charging_power": 0,
                }

        return immediate_charging

    async def _async_update_data(self) -> SemsData:
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        # Note: asyncio.TimeoutError and aiohttp.ClientError are already
        # handled by the data update coordinator.
        # async with async_timeout.timeout(10):
        try:
            data_result = await self.hass.async_add_executor_job(
                self.sems_api.getData, self.station_id
            )

            energy_storage_cabinets = await self._async_get_energy_storage_cabinets(
                data_result
            )
            batteries = await self._async_get_battery_functions(energy_storage_cabinets)
            immediate_charging = await self._async_get_immediate_charging(batteries)

        except SemsRateLimitedError as err:
            raise UpdateFailed(
                f"SEMS API rate limited (retry after {err.retry_after}s)"
            ) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        else:
            _LOGGER.debug("semsApi.getData result: %s", redact_for_log(data_result))

            inverters = data_result.get("inverter")
            inverters_by_sn: dict[str, dict[str, Any]] = {}
            if not inverters or not isinstance(inverters, list):
                raise UpdateFailed(
                    "Error communicating with API: invalid or missing inverter data. See debug logs."
                )

            # Get Inverter Data
            for inverter in inverters:
                inverter_full = inverter.get("invert_full")
                if not isinstance(inverter_full, dict):
                    continue

                name = inverter_full.get("name")
                sn = inverter_full.get("sn")
                if not isinstance(sn, str):
                    continue

                _LOGGER.debug(
                    "Found inverter attribute %s %s",
                    name,
                    redact_for_log(sn),
                )
                inverters_by_sn[sn] = inverter_full

            station_info = data_result.get("info")
            station_name = None
            if isinstance(station_info, dict):
                station_name = station_info.get("stationname")
                if not isinstance(station_name, str) or not station_name:
                    station_name = None

            for inverter_data in inverters_by_sn.values():
                inverter_data["station_id"] = self.station_id
                inverter_data["station_name"] = station_name

            # Add currency
            kpi = data_result.get("kpi")
            if not isinstance(kpi, dict):
                kpi = {}
            currency = kpi.get("currency")
            station = _normalize_station_data(data_result, kpi)

            powerflow = _normalize_rest_powerflow(data_result, kpi)
            if powerflow is not None:
                _LOGGER.debug("Found powerflow data")

            data = SemsData(
                inverters=inverters_by_sn,
                station=station,
                batteries=batteries,
                powerflow=powerflow,
                currency=currency,
                immediate_charging=immediate_charging,
                station_id=self.station_id,
                station_name=station_name,
            )
            _LOGGER.debug(
                "Resulting data: %s",
                redact_for_log(data),
            )
            return data

    @callback
    def async_apply_mqtt_powerflow_update(self, update: dict[str, Any]) -> None:
        """Merge a live MQTT powerflow update into coordinator data."""

        if self.data is None:
            return

        station_id = update.get("station_id")
        if isinstance(station_id, str) and station_id != self.station_id:
            _LOGGER.debug("Ignoring MQTT update for a different station")
            return

        powerflow = dict(self.data.powerflow or {})
        powerflow.update(update)
        self.async_set_updated_data(replace(self.data, powerflow=powerflow))


# Type alias to make type inference working for pylance
type SemsCoordinator = SemsDataUpdateCoordinator
