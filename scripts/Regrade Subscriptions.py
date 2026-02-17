#!/usr/bin/env python3
"""
Apply or regrade device subscriptions in NCM API v3 from a CSV file.

This script reads a CSV file containing device identifiers and subscription IDs, then
applies or regrades subscriptions to the corresponding devices in NCM. It processes
devices in chunks of 100 for optimal API performance and groups devices by subscription
ID for efficient batch processing.

CSV Format (case-insensitive). Device column (priority order, use one):
    - id, router_id, or "router id" (e.g. from NCM devices grid)
    - mac, mac address, mac_address, or macaddress (any format; normalized automatically)
    - serial_number, serial number, or serial
    - Subscription: subscription_id, subscription, or "subscription id"

    Example (by device ID):
        id,subscription_id
        12345,BA-NCADV
        67890,BA-NCADV
    Example (by MAC):
        mac,subscription_id
        003044A2CA75,BA-NCADV
        00:30:44:A2:CA:76,BA-NCADV
    Example (by serial):
        serial_number,subscription_id
        WC2338TA003678,BA-NCADV
"""

import csv
import os
import sys
from ncm import ncm

if len(sys.argv) < 2:
    print("Error: CSV filename required as command-line argument")
    print(f"Usage: {sys.argv[0]} <csv_filename>")
    sys.exit(1)

csv_filename = sys.argv[1]

token = os.environ.get("TOKEN") or os.environ.get("NCM_API_TOKEN")
if not token:
    print("Error: TOKEN or NCM_API_TOKEN is required for NCM API v3 (set in API Keys tab).")
    sys.exit(1)

# Device column priority: id/router_id first, then mac, then serial_number
DEVICE_COLUMN_NAMES = [
    "id", "router_id", "router id",
    "mac", "mac address", "mac_address", "macaddress",
    "serial_number", "serial number", "serial",
]
SUBSCRIPTION_COLUMN_NAMES = ["subscription_id", "subscription", "subscription id"]


def normalize_mac(value: str) -> str:
    """Normalize MAC to lowercase, no separators."""
    return value.lower().strip().replace(":", "").replace("-", "").replace(" ", "")


def find_column(fieldnames: list[str], candidates: list[str]) -> str | None:
    """Return first matching column (original case) or None. Match is case-insensitive."""
    headers = {h.lower().strip(): h for h in fieldnames}
    for c in candidates:
        if c.lower() in headers:
            return headers[c.lower()]
    return None


def chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


ncm_client = ncm.NcmClientv3(api_key=token, log_events=True)

try:
    with open(csv_filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("Error: CSV file has no header row")
            sys.exit(1)
        fieldnames = list(reader.fieldnames)
        csv_columns = [c.lower().strip() for c in fieldnames]

    device_col = find_column(fieldnames, DEVICE_COLUMN_NAMES)
    if not device_col:
        print(f"Error: No device column found. Looking for one of: {', '.join(DEVICE_COLUMN_NAMES)}")
        print(f"Available columns: {', '.join(fieldnames)}")
        sys.exit(1)

    sub_col = find_column(fieldnames, SUBSCRIPTION_COLUMN_NAMES)
    if not sub_col:
        print(f"Error: No subscription column found. Looking for one of: {', '.join(SUBSCRIPTION_COLUMN_NAMES)}")
        print(f"Available columns: {', '.join(fieldnames)}")
        sys.exit(1)

    # Detect device column type for normalization
    device_col_lower = device_col.lower().strip()
    is_mac = any(
        device_col_lower == c for c in ["mac", "mac address", "mac_address", "macaddress"]
    )

    devices = []
    with open(csv_filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get(device_col, "").strip()
            sub_id = row.get(sub_col, "").strip()
            if not raw or not sub_id:
                continue
            identifier = normalize_mac(raw) if is_mac else raw
            devices.append({"identifier": identifier, "subscription_id": sub_id})

except FileNotFoundError:
    print(f"Error: CSV file not found: {csv_filename}")
    sys.exit(1)
except Exception as e:
    print(f"Error reading CSV: {e}")
    sys.exit(1)

print(f"Using device column: '{device_col}', subscription column: '{sub_col}'")
print(f"Found {len(devices)} devices to regrade. Processing in chunks of 100...")

subscription_groups = {}
for d in devices:
    sub_id = d["subscription_id"]
    if sub_id not in subscription_groups:
        subscription_groups[sub_id] = []
    subscription_groups[sub_id].append(d["identifier"])

if devices:
    for subscription_id, identifiers in subscription_groups.items():
        print(f"Processing {len(identifiers)} devices with subscription_id: {subscription_id}")
        for chunk in chunks(identifiers, 100):
            try:
                result = ncm_client.regrade(subscription_id, chunk)
                # API may return a string (message) or a dict (e.g. success payload) on success
                if isinstance(result, str) and "error" in result.lower():
                    print(f"Chunk regrade warning for {subscription_id}: {result}")
                elif isinstance(result, dict) and (result.get("data") or result.get("id")):
                    print(f"Chunk regrade completed for {subscription_id} (API returned success payload)")
                else:
                    print(f"Chunk regrade result for {subscription_id}: {result}")
                    if result is not None and not isinstance(result, str):
                        print(f"  API response: {result}")
            except TypeError as e:
                print(f"Unexpected API response for {subscription_id}: {e}")
            except Exception as e:
                print(f"Error processing chunk for {subscription_id}: {e}")
else:
    print("No devices found in CSV file")
