"""Device helpers for the SEMS integration."""

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def device_info_for_station(
    station_id: str | None,
    station_name: str | None,
    inverter_data: dict[str, Any] | None = None,
) -> DeviceInfo:
    """Build device info for the station feed."""

    inverter_data = inverter_data or {}
    identifier = station_id or inverter_data.get("powerstation_id") or "station"
    name = station_name or inverter_data.get("station_name") or "SEMS Station"

    if not isinstance(name, str) or not name.strip():
        name = "SEMS Station"

    firmware_version = inverter_data.get("firmwareversion")
    if firmware_version in (None, ""):
        sw_version = "unknown"
    else:
        sw_version = str(firmware_version)

    # NOTE: We intentionally keep fallbacks here because not every SEMS payload
    # is guaranteed to contain `model_type`, `firmwareversion`, etc.
    return DeviceInfo(
        identifiers={(DOMAIN, str(identifier))},
        name=name,
        manufacturer="GoodWe",
        model=inverter_data.get("model_type", "unknown"),
        sw_version=sw_version,
        configuration_url=(
            f"https://semsportal.com/PowerStation/PowerStatusSnMin/{identifier}"
            if identifier
            else None
        ),
    )
