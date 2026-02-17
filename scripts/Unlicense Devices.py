#!/usr/bin/env python3
"""
Unlicense devices in NCM API v3 from a CSV file.

This script reads a CSV file containing device identifiers and removes licenses from
the corresponding devices in NCM. It processes devices in batches of 100 for optimal
API performance. Supports device ID, MAC (any format), or serial number.

CSV Format (case-insensitive). Device column (priority order, use one):
    - id, router_id, or "router id" (e.g. from NCM devices grid)
    - mac, mac address, mac_address, or macaddress (any format; normalized automatically)
    - serial_number, serial number, or serial

    Example (by device ID):
        id
        12345
        67890
    Example (by MAC):
        mac
        003044A2CA75
        00:30:44:A2:CA:76
    Example (by serial):
        serial_number
        WC2338TA003678
"""

import csv
import os
import sys
from ncm import ncm

if len(sys.argv) < 2:
    print("Error: CSV filename required as command-line argument")
    print(f"Usage: {sys.argv[0]} <csv_file_path>")
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

if not os.path.exists(csv_filename):
    print(f"Error: CSV file not found: {csv_filename}")
    sys.exit(1)

try:
    with open(csv_filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("Error: CSV file appears to be empty or invalid")
            sys.exit(1)
        fieldnames = list(reader.fieldnames)

    device_col = find_column(fieldnames, DEVICE_COLUMN_NAMES)
    if not device_col:
        print(f"Error: No device column found. Looking for one of: {', '.join(DEVICE_COLUMN_NAMES)}")
        print(f"Available columns: {', '.join(fieldnames)}")
        sys.exit(1)

    device_col_lower = device_col.lower().strip()
    is_mac = any(
        device_col_lower == c for c in ["mac", "mac address", "mac_address", "macaddress"]
    )

    identifiers = []
    with open(csv_filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row.get(device_col, "").strip()
            if not raw:
                continue
            identifier = normalize_mac(raw) if is_mac else raw
            identifiers.append(identifier)

except FileNotFoundError:
    print(f"Error: CSV file not found: {csv_filename}")
    sys.exit(1)
except Exception as e:
    print(f"Error reading CSV: {e}")
    sys.exit(1)

print(f"Using device column: '{device_col}'")
print(f"Found {len(identifiers)} devices to unlicense")

if identifiers:
    for chunk in chunks(identifiers, 100):
        try:
            result = ncm_client.unlicense_devices(chunk)
            # API may return a string (message) or a dict (e.g. success payload) on success
            if isinstance(result, str) and "error" in result.lower():
                print(f"Chunk unlicense warning: {result}")
            elif isinstance(result, dict) and (result.get("data") or result.get("id")):
                print(f"Chunk unlicense completed (API returned success payload)")
            else:
                print(f"Chunk unlicense result: {result}")
                if result is not None and not isinstance(result, str):
                    print(f"  API response: {result}")
        except TypeError as e:
            print(f"Unexpected API response: {e}")
        except Exception as e:
            print(f"Error processing chunk: {e}")
else:
    print("No device identifiers found in CSV file")
