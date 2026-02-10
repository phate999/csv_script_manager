#!/usr/bin/env python3
"""
Create NCX IP subnet resources for each LAN on routers specified by router_id, group_id, or group_name.

Uses the NCM v2 API to get each router's LANs and the NCM v3 API to create one exchange_ipsubnet_resource
per LAN. The resource name follows "site_name lan_name" (e.g. "2200-Office Primary LAN"): the site name comes
from the NCX site (attributes.name), and the LAN name from the NCM LAN API (name/description/interface_name/label)
if present, otherwise "LAN 1", "LAN 2", etc. Spaces are allowed in names. The ip attribute is the LAN CIDR.
All inputs are read from a CSV file.

CSV Format (case-insensitive). Device/group columns (priority order):
    - If present, router/device column: "id", "router_id", or "router id". One row per device; multiple rows allowed.
    - Otherwise group_id or group_name (first row used). Do not include both group_id and group_name.

    Required:
        - ncx_network_id: NCX network ID that the sites/resources belong to
        - site_name (or "site name"): NCX site name to look up the site; site is always resolved by this column, not by router name.

    Example (by router):
        router_id,ncx_network_id,site_name
        12345,abcd-efgh-ijkl,Branch Alpha
        67890,abcd-efgh-ijkl,Site 67890

    Example (by group):
        group_id,ncx_network_id,site_name
        1234,abcd-efgh-ijkl,My NCX Site

Usage:
    python "Create NCX LAN Resources.py" <config_csv_path>

Requirements:
    - NCM Python helper module `ncm` available in PYTHONPATH
    - API keys and token via environment (or API Keys tab)
"""

import csv
import ipaddress
import os
import sys

from ncm import ncm


def load_config_from_csv(csv_filename: str) -> tuple[str, list[tuple[str, str, str]]]:
    """
    Read CSV and determine mode (router_id, group_id, or group_name) and rows.
    Returns (mode, [(identifier, ncx_network_id, site_name), ...]). site_name is required per row.
    """
    try:
        with open(csv_filename, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("CSV file has no header row")

            headers = {h.lower().strip(): h for h in reader.fieldnames}

            network_key = next(
                (headers[k] for k in ["ncx_network_id", "ncx network id"] if k in headers),
                None,
            )
            if not network_key:
                raise ValueError(
                    "CSV must contain 'ncx_network_id'. "
                    f"(found: {reader.fieldnames})"
                )

            site_name_key = next(
                (headers[k] for k in ["site_name", "site name"] if k in headers),
                None,
            )
            if not site_name_key:
                raise ValueError(
                    "CSV must contain 'site_name' (or 'site name'); site is looked up by this column, not by router name. "
                    f"(found: {reader.fieldnames})"
                )

            router_key = next(
                (headers[k] for k in ["id", "router_id", "router id"] if k in headers), None
            )
            group_id_key = next(
                (headers[k] for k in ["group_id", "group id"] if k in headers), None
            )
            group_name_key = next(
                (headers[k] for k in ["group_name", "group name"] if k in headers), None
            )

            if router_key:
                mode = "router_id"
            elif group_id_key and group_name_key:
                raise ValueError(
                    "CSV must not contain both 'group_id' and 'group_name'; use one or the other. "
                    f"(found: {reader.fieldnames})"
                )
            elif group_id_key:
                mode = "group_id"
            elif group_name_key:
                mode = "group_name"
            else:
                raise ValueError(
                    "CSV must contain a router/device column ('id' or 'router_id') or a group "
                    "column ('group_id' or 'group_name'). " f"(found: {reader.fieldnames})"
                )
            rows = []

            for row in reader:
                network_id = row.get(network_key, "").strip()
                site_name = row.get(site_name_key, "").strip()
                if not network_id or not site_name:
                    continue
                if mode == "router_id":
                    ident = row.get(router_key, "").strip()
                    if ident:
                        rows.append((ident, network_id, site_name))
                elif mode == "group_id":
                    ident = row.get(group_id_key, "").strip()
                    if ident:
                        rows.append((ident, network_id, site_name))
                        break
                else:
                    ident = row.get(group_name_key, "").strip()
                    if ident:
                        rows.append((ident, network_id, site_name))
                        break

            if not rows:
                raise ValueError(
                    f"No data row with {mode}, ncx_network_id, and site_name found"
                )
            return mode, rows
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {csv_filename}") from None


def build_api_keys() -> dict:
    """Build API keys dict, preferring environment variables."""
    api_keys = {
        "X-ECM-API-ID": os.environ.get("X_ECM_API_ID", ""),
        "X-ECM-API-KEY": os.environ.get("X_ECM_API_KEY", ""),
        "X-CP-API-ID": os.environ.get("X_CP_API_ID", ""),
        "X-CP-API-KEY": os.environ.get("X_CP_API_KEY", ""),
        "token": os.environ.get("TOKEN") or os.environ.get("NCM_API_TOKEN", ""),
    }
    return api_keys


def get_site(
    n3: ncm.NcmClientv3, router: dict, site_name_override: str
) -> dict | None:
    """Get the NCX site by name (from CSV site_name column). Site must be associated with this router."""
    name_to_use = site_name_override.strip()
    sites = n3.get_exchange_sites(name=name_to_use)
    if not sites:
        print(f"Site not found: no site returned for name {name_to_use!r} (router {router['id']} {router['name']}).")
        return None

    first = sites[0]
    if isinstance(first, str):
        print(f"Site lookup failed for name {name_to_use!r}: {first}")
        return None
    if not isinstance(first, dict):
        detail = repr(first)
        if len(detail) > 300:
            detail = detail[:297] + "..."
        print(
            f"Site lookup for {name_to_use!r} returned unexpected type {type(first).__name__} instead of site data.\n  Response: {detail}"
        )
        return None

    site_router_id = ""
    try:
        site_router_id = first["relationships"]["endpoints"]["data"][0]["id"]
        if str(site_router_id) != str(router["id"]):
            raise ValueError
    except (KeyError, IndexError, ValueError, TypeError) as e:
        rel = first.get("relationships", {})
        detail = repr(rel) if rel else "(no relationships)"
        if len(detail) > 250:
            detail = detail[:247] + "..."
        print(
            f"Site {name_to_use!r} does not match router or has unexpected structure: "
            f"site endpoint {site_router_id or '?'} != router {router['id']}.\n  "
            f"Error: {type(e).__name__}: {e}\n  "
            f"Site relationships: {detail}"
        )
        return None

    return first


def get_lans(n2: ncm.NcmClientv2, router: dict) -> list[tuple[str, str]]:
    """Return list of (display_name, cidr) for each LAN. Display name from API if present, else 'LAN 1', 'LAN 2', ..."""
    url = f"{n2.base_url}/routers/{router['id']}/lans/"
    response = n2.session.get(url)
    if not response.ok:
        print(f"Failed to get LANs for router {router['id']}: {response.text}")
        return []

    lans: list[tuple[str, str]] = []
    for i, lan in enumerate(response.json()):
        try:
            network = ipaddress.ip_network(
                f"{lan['ip_address']}/{lan['netmask']}", strict=False
            )
            cidr = str(network)
            # Prefer name/description/label from API; else "LAN 1", "LAN 2", ...
            display = (
                (lan.get("name") or lan.get("description") or lan.get("interface_name") or lan.get("label") or "").strip()
                or f"LAN {i + 1}"
            )
            lans.append((display, cidr))
        except (KeyError, ValueError):
            continue
    return lans


def create_ncx_lan_resources(
    mode: str, rows: list[tuple[str, str, str]]
) -> None:
    """Create one NCX IP subnet resource per LAN for each router; name is 'site_name lan_name', ip is LAN CIDR."""
    api_keys = build_api_keys()
    token = api_keys.get("token") or os.environ.get("TOKEN") or os.environ.get("NCM_API_TOKEN")
    if not token:
        print("Error: TOKEN or NCM_API_TOKEN is required for NCX v3 API (set in API Keys tab).")
        return

    n2 = ncm.NcmClientv2(api_keys=api_keys, log_events=False)
    n3 = ncm.NcmClientv3(api_key=token, log_events=False)

    for identifier, ncx_network_id, site_name_override in rows:
        if mode == "router_id":
            routers = n2.get_routers(id__in=[identifier])
        else:
            routers = n2.get_routers(group=identifier, limit="all")

        if not routers:
            print(f"No routers found for {mode}={identifier!r}.")
            continue

        for router in routers:
            print(
                f'Creating NCX LAN resources for router {router["id"]} {router["name"]} '
                f"in network {ncx_network_id}..."
            )
            site = get_site(n3, router, site_name_override=site_name_override)
            if not site:
                continue

            lans = get_lans(n2, router)
            if not lans:
                print(f"No LANs found for router {router['id']} {router['name']}.")
                continue

            # API returns JSON:API style: site name is under attributes.name
            site_display_name = (site.get("attributes") or {}).get("name") or site.get("name") or site.get("id") or "site"

            any_failed = False
            for lan_display_name, cidr in lans:
                # Resource name: "site_name lan_name" (e.g. "2200-Office Primary LAN"); spaces are allowed by API
                name = f"{site_display_name} {lan_display_name}"
                if len(name) < 3:
                    print(
                        f"Skipping LAN {cidr!r}: resource name must be at least 3 characters (router {router['name']})."
                    )
                    any_failed = True
                    continue
                try:
                    resource = n3.create_exchange_resource(
                        site_id=site["id"],
                        resource_name=name,
                        resource_type="exchange_ipsubnet_resources",
                        ip=cidr,
                    )
                except Exception as e:
                    print(
                        f"Error creating NCX LAN resource {name!r} ({cidr}) for router {router['name']}: "
                        f"{type(e).__name__}: {e}"
                    )
                    any_failed = True
                    continue
                if isinstance(resource, str):
                    if "overlapping_resource" not in resource:
                        print(resource)
                        any_failed = True
                    continue
                if isinstance(resource, dict) and (resource.get("data") or resource.get("id")):
                    pass
                else:
                    print(
                        f"Error creating NCX LAN resource {name!r} for router {router['name']}. "
                        "Check subscriptions (router/site may need NCX license)."
                    )
                    if resource is not None:
                        print(f"  API response: {resource}")
                    any_failed = True
                    continue
                print(
                    f"Created NCX LAN resource {name!r} ({cidr}) for router "
                    f'{router["name"]}, site {site_display_name}.'
                )
            if not any_failed:
                print("Success!\n")


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python "Create NCX LAN Resources.py" <config_csv_path>')
        sys.exit(1)

    csv_filename = sys.argv[1]

    try:
        mode, rows = load_config_from_csv(csv_filename)
    except Exception as exc:
        print(f"Error reading configuration from CSV: {exc}")
        sys.exit(1)

    create_ncx_lan_resources(mode, rows)


if __name__ == "__main__":
    main()
