# MQTT Payload Decoding Results & Next Steps

## Summary

All hex-encoded MQTT payloads from the browser traffic have been successfully decoded and analyzed. **The payloads contain standard MQTT protocol packets with no anomalies.**

## Decoded Browser Traffic Sequence

### 1. CONNECT (Sent to Broker)

**Hex**: `10f405...` (759 bytes)

```json
{
  "message_type": "CONNECT",
  "protocol_name": "MQTT",
  "protocol_level": 4, // MQTT v3.1.1
  "client_id": "SEMS_PLUS_WebClient_adc9ee364a7a44e7a5b227580342fe92",
  "username": "<base64-encoded token>",
  "password": "<344-byte base64-encoded token>",
  "keep_alive": 60,
  "clean_session": true
}
```

### 2. CONNACK (Received from Broker)

**Hex**: `20020000` (4 bytes)

```json
{
  "message_type": "CONNACK",
  "session_present": false,
  "return_code": 0,
  "return_code_name": "Connection Accepted"
}
```

### 3. SUBSCRIBE (Sent to Broker)

**Hex**: `8245f3a7...` (71 bytes)

```json
{
  "message_type": "SUBSCRIBE",
  "packet_id": 62375,
  "topics": [
    {
      "topic": "/goodwe/second-data/station/316c15e5-f0a5-4682-b58c-911d1061e886",
      "qos": 0
    }
  ]
}
```

### 4. SUBACK (Received from Broker)

**Hex**: `9003f3a700` (5 bytes)

```json
{
  "message_type": "SUBACK",
  "packet_id": 62375, // Matches SUBSCRIBE packet ID
  "return_codes": [0] // Subscription accepted
}
```

### 5. PUBLISH #1 (Received from Broker)

**Hex**: `30f102...` (372 bytes)

```json
{
  "message_type": "PUBLISH",
  "topic": "/goodwe/second-data/station/316c15e5-f0a5-4682-b58c-911d1061e886",
  "qos": 0,
  "payload": {
    "traceId": "c0107705f98985cb30eeb664eee0ca98",
    "pSystem": "0.0",
    "pConsum": "0.88826",
    "pBat": "0.88826",
    "pGrid": "0.0",
    "pAc": "0.88826",
    "fAc": "49.97",
    "qAc": "0.0",
    "pf": "-0.025",
    "soc": "33.0",
    "flows": { "pBat": ["pConsum"] },
    "time": "2026-09-19 23:47:18",
    "stationId": "316c15e5-f0a5-4682-b58c-911d1061e886"
  }
}
```

### 6. PUBLISH #2 (Received from Broker)

**Hex**: `30880300...` (395 bytes)
Similar to PUBLISH #1 with updated values at 2026-09-19 23:47:23

### 7. Heartbeat (Every 30 seconds)

**PINGREQ (Sent)**: `c000` (2 bytes)

- Message type: PINGREQ (12)
- Flags: 0
- Remaining length: 0

**PINGRESP (Received)**: `d000` (2 bytes)

- Message type: PINGRESP (13)
- Flags: 0
- Remaining length: 0

## Analysis

### ✓ What's Normal

- All MQTT packets are standard MQTT v3.1.1 protocol
- CONNECT/CONNACK handshake succeeded (return code 0)
- SUBSCRIBE/SUBACK handshake succeeded with matching packet IDs
- PUBLISH payloads are valid UTF-8 JSON
- Heartbeat ping/pong is standard MQTT keep-alive (60-second interval)
- No unusual flags, encoding issues, or protocol violations

### ⚠️ Questions to Investigate

1. **Are our credentials identical?**
   - The browser uses username/password from the same `getMqttConfig` API call
   - We should verify we're getting the exact same credentials

2. **Are we sending the same CONNECT packet?**
   - Same protocol version (v3.1.1) ✓
   - Same client ID format?
   - Same keep-alive (60s) ✓
   - Same clean_session flag ✓

3. **Are we sending SUBSCRIBE with the correct topic?**
   - Topic format: `/goodwe/second-data/station/{station-id}`
   - QoS: 0 (confirmed in code)

## Artifacts Created

- **logs/mqtt_payloads_decoded.json** - Full decoded payload dump
- **MQTT_PROTOCOL_ANALYSIS.md** - Protocol analysis and version details
- **scripts/decode_mqtt_payloads.py** - Reusable decoder utility

Usage: `python scripts/decode_mqtt_payloads.py --file PAYLOADS.md`

## Next Debugging Steps

### Immediate (Do These First)

1. Run the updated local_api_test.py with protocol logging enabled:

   ```bash
   python scripts/local_api_test.py --api-only  # Just REST + config
   ```

   This will save MQTT config to `logs/*_mqtt_config.json` for inspection

2. Check if our credentials match the browser's:
   - Compare `logs/*_mqtt_config.json` with what the browser is using
   - Verify client_id, username, password length and format

### If Credentials Match

3. Run full MQTT capture with protocol debugging:

   ```bash
   python scripts/local_api_test.py --duration 30
   ```

   This will log:
   - Stage 1: CONNECT packet details before sending
   - Stage 2: CONNACK receipt confirmation
   - Stage 3: SUBSCRIBE packet details
   - Stage 4: SUBACK receipt confirmation
   - Plus paho-mqtt's raw protocol logs with redacted station IDs

4. Capture our CONNECT/SUBSCRIBE packets from the logs and decode them:

   ```bash
   python scripts/decode_mqtt_payloads.py --file logs/*_mqtt_config.json
   ```

5. Compare side-by-side:
   - Browser CONNECT vs. Our CONNECT (via protocol logs)
   - Browser SUBSCRIBE vs. Our SUBSCRIBE (via protocol logs)

### If Packets Match But Still No Data

- Check broker rate limiting or connection limiting
- Verify both connections don't have conflicting subscription filters
- Check if there's a single-client-per-credential-set limit

## Files Modified

- `custom_components/sems_au/const.py` - Added redact_text() for embedded UUIDs
- `custom_components/sems_au/sems_mqtt.py` - Added protocol logging with redaction
- `scripts/local_api_test.py` - Fixed logger pass-through, added MQTT config capture
- `scripts/decode_mqtt_payloads.py` - New utility for decoding hex MQTT packets
