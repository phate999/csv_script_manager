#!/usr/bin/env python3
"""
Create a CSV report of custom alerts from NCM.

Does not use CSV input. Run with "No CSV Input" in the Run Script dialog.
Fetches all alerts with type=custom_alert from the NCM API v2 and writes them to a CSV file
in the csv_files folder. Sets the output file as the last file (.last_file.txt) for the CSV Script Manager.
"""

import csv
import os
import sys
from datetime import datetime

from ncm import ncm


def build_api_keys() -> dict:
    """Build API keys dict from environment."""
    api_keys = {
        "X-ECM-API-ID": os.environ.get("X_ECM_API_ID", ""),
        "X-ECM-API-KEY": os.environ.get("X_ECM_API_KEY", ""),
        "X-CP-API-ID": os.environ.get("X_CP_API_ID", ""),
        "X-CP-API-KEY": os.environ.get("X_CP_API_KEY", ""),
    }
    return {k: v for k, v in api_keys.items() if v}


def get_custom_alerts(n2: ncm.NcmClientv2) -> list[dict]:
    """Fetch all alerts with type=custom_alert from NCM API v2. Handles pagination if present."""
    url = f"{n2.base_url.rstrip('/')}/alerts/"
    params = {"type": "custom_alert"}
    all_alerts = []
    while url:
        response = n2.session.get(url, params=params)
        params = None  # next page URL has its own query string
        if not response.ok:
            print(f"API error {response.status_code}: {response.text}")
            return all_alerts
        data = response.json()
        # Response may be list or dict with results/meta
        if isinstance(data, list):
            all_alerts.extend(a for a in data if a.get("type") == "custom_alert")
            break
        if isinstance(data, dict):
            results = data.get("results") or data.get("data") or []
            all_alerts.extend(a for a in results if a.get("type") == "custom_alert")
            # Pagination: next link
            url = None
            for link_key in ("next", "links"):
                rest = data.get(link_key)
                if isinstance(rest, str) and rest:
                    url = rest
                    break
                if isinstance(rest, dict) and rest.get("next"):
                    url = rest["next"]
                    break
            if not url and not results:
                break
        else:
            break
    return all_alerts


def alert_to_row(alert: dict) -> dict:
    """Flatten one alert into a CSV row (plain keys and string values)."""
    info = alert.get("info") or {}
    if isinstance(info.get("time"), list):
        info_time = " ".join(str(t) for t in info["time"])
    else:
        info_time = str(info.get("time", ""))
    router_url = alert.get("router") or ""
    router_id = ""
    if router_url:
        parts = router_url.rstrip("/").split("/")
        if parts:
            router_id = parts[-1]
    return {
        "created_at": alert.get("created_at", ""),
        "created_at_timeuuid": alert.get("created_at_timeuuid", ""),
        "detected_at": alert.get("detected_at", ""),
        "friendly_info": alert.get("friendly_info", ""),
        "info_message": info.get("message", ""),
        "info_time": info_time,
        "info_title": info.get("title", ""),
        "info_type": info.get("type", ""),
        "info_uptime": str(info.get("uptime", "")),
        "router_id": router_id,
        "router_url": router_url,
        "type": alert.get("type", ""),
    }


def main() -> None:
    api_keys = build_api_keys()
    if not api_keys:
        print(
            "Error: API keys not set. Set X_ECM_API_ID, X_ECM_API_KEY, X_CP_API_ID, X_CP_API_KEY "
            "(environment or API Keys tab)."
        )
        sys.exit(1)

    n2 = ncm.NcmClientv2(api_keys=api_keys, log_events=False)
    alerts = get_custom_alerts(n2)
    if not alerts:
        print("No custom alerts found.")
    else:
        print(f"Found {len(alerts)} custom alert(s).")

    # Determine app directory robustly: prefer sys.argv[0] (set by wrapper) over __file__
    script_path = os.path.abspath(sys.argv[0] or __file__)
    # script_path is .../scripts/Custom Alerts Report.py when run via wrapper or directly
    scripts_dir = os.path.dirname(script_path)
    app_dir = os.path.dirname(scripts_dir)
    csv_dir = os.path.join(app_dir, "csv_files")
    os.makedirs(csv_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_filename = f"custom_alerts_report_{timestamp}.csv"
    out_path = os.path.join(csv_dir, out_filename)

    fieldnames = [
        "created_at",
        "created_at_timeuuid",
        "detected_at",
        "friendly_info",
        "info_message",
        "info_time",
        "info_title",
        "info_type",
        "info_uptime",
        "router_id",
        "router_url",
        "type",
    ]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for alert in alerts:
            writer.writerow(alert_to_row(alert))

    print(f"Wrote {out_path}")

    last_file_path = os.path.join(app_dir, ".last_file.txt")
    with open(last_file_path, "w", encoding="utf-8") as f:
        f.write(out_filename)
    print(f"Set last file to {out_filename}")


if __name__ == "__main__":
    main()
