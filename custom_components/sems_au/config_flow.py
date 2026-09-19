"""Config flow for sems integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    CONF_REGION,
    CONF_STATION_ID,
    DEFAULT_SEMS_REGION,
    DOMAIN,
    SEMS_REGIONS,
    redact_for_log,
)
from .sems_api import SemsApi

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default=DEFAULT_SEMS_REGION): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(SEMS_REGIONS),
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_SCAN_INTERVAL, description={"suggested_value": 60}): int,
    }
)


def _normalize_station_ids(raw: Any) -> list[str]:
    """Normalize a getPowerStationIds result to a list of station ID strings."""
    if isinstance(raw, str) and raw:
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return []


def _station_entry_title(station_id: str, station_name: str | None = None) -> str:
    """Return a station-scoped title for the config entry."""
    if station_name and station_name.strip():
        return f"{station_name}: {station_id}"
    return f"Station {station_id}"


async def validate_credentials(hass: HomeAssistant, data: dict[str, Any]) -> SemsApi:
    """Validate credentials and return an authenticated API client."""
    _LOGGER.debug(
        "SEMS - Validating credentials for user: %s",
        redact_for_log(data.get(CONF_USERNAME, "")),
    )
    api = SemsApi(
        hass,
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data.get(CONF_REGION, DEFAULT_SEMS_REGION),
    )
    authenticated = await hass.async_add_executor_job(api.test_authentication)
    if not authenticated:
        raise InvalidAuth
    return api


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for sems."""

    VERSION = 3

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors: dict[str, str] = {}

        try:
            api = await validate_credentials(self.hass, user_input)

            _LOGGER.debug("SEMS - Credentials valid, fetching station IDs")
            raw_ids = await self.hass.async_add_executor_job(api.getPowerStationIds)
            _LOGGER.debug("SEMS - Found power station IDs: %s", redact_for_log(raw_ids))

            station_ids = _normalize_station_ids(raw_ids)

            if not station_ids:
                errors["base"] = "no_stations_found"
            else:
                # Schedule flows for any additional stations so all are auto-added.
                # Users can disable individual entities or devices via the HA UI after setup.
                for station_id in station_ids[1:]:
                    self.hass.async_create_task(
                        self.hass.config_entries.flow.async_init(
                            DOMAIN,
                            context={"source": config_entries.SOURCE_IMPORT},
                            data={**user_input, CONF_STATION_ID: station_id},
                        )
                    )
                station_id = station_ids[0]
                station_name = None
                try:
                    station_data = await self.hass.async_add_executor_job(
                        api.getData, station_id
                    )
                    if isinstance(station_data, dict):
                        info = station_data.get("info")
                        if isinstance(info, dict):
                            station_name = info.get("stationname")
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.debug(
                        "SEMS - Unable to resolve station name for %s; using fallback title",
                        redact_for_log(station_id),
                    )
                await self.async_set_unique_id(station_id)
                self._abort_if_unique_id_configured()
                _LOGGER.debug(
                    "SEMS - Creating entry for station %s",
                    redact_for_log(station_id),
                )
                return self.async_create_entry(
                    title=_station_entry_title(station_id, station_name),
                    data={**user_input, CONF_STATION_ID: station_id},
                )

        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except AbortFlow:
            raise
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Auto-create an entry for an additional discovered station."""
        station_id = str(import_data.get(CONF_STATION_ID, ""))
        await self.async_set_unique_id(station_id)
        self._abort_if_unique_id_configured()
        _LOGGER.debug(
            "SEMS - Auto-adding station %s from multi-station discovery",
            redact_for_log(station_id),
        )
        station_name = None
        if isinstance(import_data, dict):
            station_name = import_data.get("station_name")
        return self.async_create_entry(
            title=_station_entry_title(station_id, station_name),
            data=import_data,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
