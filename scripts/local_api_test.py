#!/usr/bin/env python3
"""Capture SEMS REST and MQTT data without running Home Assistant."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import ssl
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiomqtt
from dotenv import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from custom_components.sems_au.const import (  # noqa: E402
    DEFAULT_SEMS_REGION,
)
from custom_components.sems_au.sems_api import SemsApi  # noqa: E402
from custom_components.sems_au.sems_mqtt import (  # noqa: E402
    SemsMqttConfig,
    decode_mqtt_payload,
)

_RECONNECT_DELAY = 5


class MinimalHass:
    """Minimal Home Assistant stub for local API testing."""

    async def async_add_executor_job(self, func, *args):
        """Execute a synchronous function in a worker thread."""
        return await asyncio.to_thread(func, *args)


def _parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--duration",
        type=float,
        help="Stop after this many seconds instead of waiting for Ctrl+C",
    )
    return parser.parse_args()


def _station_id_from_response(value: Any) -> str | None:
    """Return the first station ID from the supported API response shapes."""
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list) and value:
        first = value[0]
        return str(first) if first else None
    return None


def _capture_record(topic: str, payload: bytes) -> dict[str, Any]:
    """Build a lossless, analysis-friendly record for one MQTT message."""
    record: dict[str, Any] = {
        "received_at": datetime.now(UTC).isoformat(),
        "topic": topic,
    }
    try:
        raw_text = payload.decode("utf-8")
    except UnicodeDecodeError:
        record.update(
            {
                "raw_encoding": "base64",
                "raw_payload": base64.b64encode(payload).decode("ascii"),
                "parsed_payload": None,
            }
        )
    else:
        record.update(
            {
                "raw_encoding": "utf-8",
                "raw_payload": raw_text,
                "parsed_payload": decode_mqtt_payload(payload),
            }
        )
    return record


async def _capture_mqtt(
    api: SemsApi,
    station_id: str,
    output_file: Path,
    duration: float | None,
) -> int:
    """Stream MQTT messages to the console and a JSON Lines capture file."""
    topic = f"/goodwe/second-data/station/{station_id}"
    deadline = asyncio.get_running_loop().time() + duration if duration else None
    message_count = 0

    with output_file.open("a", encoding="utf-8") as capture:
        while deadline is None or asyncio.get_running_loop().time() < deadline:
            try:
                config_data = await asyncio.to_thread(api.getMqttConfig)
                config = SemsMqttConfig.from_api(config_data)
                tls_context = ssl.create_default_context() if config.use_tls else None

                async with aiomqtt.Client(
                    hostname=config.hostname,
                    port=config.port,
                    username=config.username,
                    password=config.password,
                    identifier=config.client_id,
                    protocol=aiomqtt.ProtocolVersion.V311,
                    transport="websockets",
                    tls_context=tls_context,
                    websocket_path=config.websocket_path,
                    websocket_headers={"Origin": config.websocket_origin},
                    keepalive=60,
                ) as client:
                    await client.subscribe(topic)
                    logging.info(
                        "Connected to %s:%s and subscribed to %s",
                        config.hostname,
                        config.port,
                        topic,
                    )

                    async def consume_messages() -> None:
                        nonlocal message_count
                        logging.debug("Starting message consumption loop")
                        message_received_time = asyncio.get_running_loop().time()
                        async for message in client.messages:
                            message_received_time = asyncio.get_running_loop().time()
                            record = _capture_record(
                                str(message.topic), bytes(message.payload)
                            )
                            capture.write(
                                json.dumps(record, ensure_ascii=False, default=str)
                                + "\n"
                            )
                            capture.flush()
                            message_count += 1
                            logging.info(
                                "MQTT message %s topic=%s payload=%s",
                                message_count,
                                record["topic"],
                                json.dumps(
                                    record["parsed_payload"],
                                    ensure_ascii=False,
                                    default=str,
                                ),
                            )

                    if deadline is None:
                        await consume_messages()
                    else:
                        async with asyncio.timeout_at(deadline):
                            await consume_messages()
            except TimeoutError:
                logging.info("Deadline reached; stopping capture")
                break
            except (aiomqtt.MqttError, ValueError) as err:
                logging.warning(
                    "MQTT connection failed (%s); retrying in %s seconds",
                    err,
                    _RECONNECT_DELAY,
                )
                if deadline is not None:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(_RECONNECT_DELAY, remaining))
                else:
                    await asyncio.sleep(_RECONNECT_DELAY)
            except Exception as err:
                logging.error("Unexpected error in MQTT capture: %s", err, exc_info=True)
                raise
        
        if message_count == 0:
            logging.warning(
                "No MQTT messages received. This usually means no data is currently being "
                "published on the topic. The connection and subscription succeeded, but the "
                "device may not be actively sending data at this moment. Try running again "
                "or checking the device status via the REST API."
            )

    return message_count


async def _async_main(args: argparse.Namespace) -> None:
    """Run the local REST snapshot and MQTT capture."""
    load_dotenv(REPOSITORY_ROOT / ".env")
    log_dir = REPOSITORY_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{timestamp}_local_test.log"
    mqtt_file = log_dir / f"{timestamp}_mqtt_messages.jsonl"

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )

    username = os.getenv("SEMS_USERNAME")
    password = os.getenv("SEMS_PASSWORD")
    if not username or not password:
        raise SystemExit("SEMS_USERNAME and SEMS_PASSWORD must be set in .env")

    logging.info("Authenticating SEMS account %s", username)
    api = SemsApi(MinimalHass(), username, password)
    authenticated = await asyncio.to_thread(api.test_authentication)
    if not authenticated:
        raise SystemExit("Authentication failed")

    power_stations = await asyncio.to_thread(api.getPowerStationIds)
    station_list_file = log_dir / f"{timestamp}_raw_getPowerStationIds.json"
    station_list_file.write_text(
        json.dumps({"data": power_stations}, indent=2), encoding="utf-8"
    )

    station_id = os.getenv("SEMS_POWER_STATION_ID") or _station_id_from_response(
        power_stations
    )
    if not station_id:
        raise SystemExit(f"No usable power station ID returned: {power_stations!r}")

    logging.info("Fetching initial REST snapshot for %s", station_id)
    monitoring_data = await asyncio.to_thread(api.getData, station_id)
    if not monitoring_data:
        raise SystemExit("Failed to fetch initial monitoring data")
    monitoring_file = log_dir / f"{timestamp}_raw_monitoring_data.json"
    monitoring_file.write_text(json.dumps(monitoring_data, indent=2), encoding="utf-8")

    logging.info("Initial REST snapshot: %s", monitoring_file)
    logging.info("MQTT capture: %s", mqtt_file)
    logging.info(
        "Streaming live messages from region %s; press Ctrl+C to stop",
        DEFAULT_SEMS_REGION,
    )
    message_count = await _capture_mqtt(api, station_id, mqtt_file, args.duration)
    logging.info("Capture complete: %s MQTT messages written", message_count)


def main() -> None:
    """Run the local capture and handle an interactive stop cleanly."""
    try:
        asyncio.run(_async_main(_parse_arguments()))
    except KeyboardInterrupt:
        logging.info("Capture stopped by user; all received messages were flushed")


if __name__ == "__main__":
    main()
