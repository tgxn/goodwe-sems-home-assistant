"""Tests for SEMS device helpers."""

from custom_components.sems_au.device import device_info_for_station


def test_device_info_sw_version_is_string_for_numeric_firmware() -> None:
    """Numeric firmware versions should be converted to strings."""
    device_info = device_info_for_station(
        "station-123",
        "Test Solar Farm",
        {"name": "Test Inverter", "model_type": "GW3000-NS", "firmwareversion": 1717.0},
    )

    assert device_info["sw_version"] == "1717.0"
    assert isinstance(device_info["sw_version"], str)


def test_device_info_sw_version_defaults_to_unknown_for_missing_firmware() -> None:
    """Missing firmware versions should use a string fallback."""
    device_info = device_info_for_station(
        "station-123",
        "Test Solar Farm",
        {"name": "Test Inverter", "model_type": "GW3000-NS"},
    )

    assert device_info["sw_version"] == "unknown"


def test_device_info_uses_station_name() -> None:
    """The HA device should represent the station feed."""
    device_info = device_info_for_station(
        "station-123",
        "Test Solar Farm",
        {
            "name": "Inverter 1",
            "model_type": "GW3000-NS",
            "powerstation_id": "station-123",
            "station_name": "Test Solar Farm",
        },
    )

    assert device_info["name"] == "Test Solar Farm"
    assert device_info["identifiers"] == {("sems_au", "station-123")}
