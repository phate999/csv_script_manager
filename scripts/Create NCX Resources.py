#!/usr/bin/env python3
"""
Create NCX resources from CSV: one resource per row (IP/subnet or FQDN), classified automatically.

Uses the NCM v2 API to resolve routers and the NCM v3 API to create NCX resources.
Each row specifies a router (or group), network, optional site name, and the resource value (IP, subnet, or domain).
Use exactly one of: router_id, group_id, or group_name. All inputs are read from a CSV file.

CSV Format (case-insensitive). Device/group columns (priority order):
    - If present, router/device column: "id", "router_id", or "router id". One row per resource; multiple rows allowed.
    - Otherwise group_id or group_name (first row used). Do not include both group_id and group_name.

    Required:
        - ncx_network_id: NCX network ID that the sites/resources belong to
        - resource (or "target"): The value to create — IP address, subnet (e.g. 192.168.0.0/24), or domain (e.g. app.example.com or *.example.com). Type is detected automatically.

    Optional:
        - site_name (or "site name"): NCX site name to use; if omitted, site is looked up by router name.
        - resource_name (or "resource name"): Display name for the resource; if omitted, the resource value is used as the name.

    Example (by router):
        router_id,ncx_network_id,site_name,resource,resource_name
        12345,abcd-efgh-ijkl,Branch Alpha,192.168.0.0/24,Office LAN
        12345,abcd-efgh-ijkl,,*.api.example.com,Wildcard API

    Example (by group, one resource per router in group):
        group_id,ncx_network_id,resource
        1234,abcd-efgh-ijkl,10.0.0.0/24

Usage:
    python "Create NCX Resources.py" <config_csv_path>

Requirements:
    - NCM Python helper module `ncm` available in PYTHONPATH
    - NCM / NCX API access
    - API keys and token via environment (or API Keys tab): X_ECM_API_ID, X_ECM_API_KEY,
      X_CP_API_ID, X_CP_API_KEY, TOKEN or NCM_API_TOKEN
"""

import csv
import ipaddress
import os
import sys

from ncm import ncm


def classify_resource_target(value: str) -> tuple[str, dict[str, str]]:
    """
    Classify a target string as an IP/subnet or (wildcard) FQDN and
    return (resource_type, extra_kwargs) for create_exchange_resource().
    """
    # First, try to interpret as IPv4 address or subnet
    try:
        ipaddress.ip_network(value, strict=False)
        return "exchange_ipsubnet_resources", {"ip": value}
    except ValueError:
        # Not an IP/subnet; treat as domain
        if value.startswith("*."):
            return "exchange_wildcard_fqdn_resources", {"domain": value}
        return "exchange_fqdn_resources", {"domain": value}


def load_config_from_csv(
    csv_filename: str,
) -> tuple[str, list[tuple[str, str, str | None, str, str | None]]]:
    """
    Read CSV and determine mode (router_id, group_id, or group_name) and rows.
    Returns (mode, [(identifier, ncx_network_id, site_name_or_none, resource_value, resource_name_or_none), ...]).
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

            resource_key = next(
                (headers[k] for k in ["resource", "target"] if k in headers),
                None,
            )
            if not resource_key:
                raise ValueError(
                    "CSV must contain 'resource' or 'target' (the value to create: IP, subnet, or domain). "
                    f"(found: {reader.fieldnames})"
                )

            site_name_key = next(
                (headers[k] for k in ["site_name", "site name"] if k in headers),
                None,
            )
            resource_name_key = next(
                (headers[k] for k in ["resource_name", "resource name"] if k in headers),
                None,
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
                resource_value = row.get(resource_key, "").strip()
                if not network_id or not resource_value:
                    continue
                site_name = row.get(site_name_key or "", "").strip() or None
                resource_name = row.get(resource_name_key or "", "").strip() or None
                if mode == "router_id":
                    ident = row.get(router_key, "").strip()
                    if ident:
                        rows.append((ident, network_id, site_name, resource_value, resource_name))
                elif mode == "group_id":
                    ident = row.get(group_id_key, "").strip()
                    if ident:
                        rows.append((ident, network_id, site_name, resource_value, resource_name))
                        break
                else:
                    ident = row.get(group_name_key, "").strip()
                    if ident:
                        rows.append((ident, network_id, site_name, resource_value, resource_name))
                        break

            if not rows:
                raise ValueError(
                    f"No data row with {mode}, ncx_network_id, and resource found"
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
    n3: ncm.NcmClientv3, router: dict, site_name_override: str | None = None
) -> dict | None:
    """
    Get the NCX site for the given router.
    If site_name_override is set, look up site by that name; otherwise look up by router name.
    The chosen site must be associated with this router (validated via relationships).
    """
    name_to_use = (site_name_override or router["name"]).strip()
    sites = n3.get_exchange_sites(name=name_to_use)
    if not sites:
        print(
            f'Site not found for router {router["id"]} {router["name"]}'
            + (f' (site_name={site_name_override!r})' if site_name_override else "")
            + "."
        )
        return None

    first = sites[0]
    if not isinstance(first, dict):
        detail = repr(first)
        if len(detail) > 300:
            detail = detail[:297] + "..."
        print(
            f'Site data for router {router["id"]} {router["name"]} has unexpected format '
            f"(expected dict, got {type(first).__name__}); skipping.\n  Response: {detail}"
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
            f"Site exists but wrong router or unexpected structure: "
            f"{site_router_id or '?'} != {router['id']}\n  "
            f"Error: {type(e).__name__}: {e}\n  "
            f"Site relationships: {detail}"
        )
        return None

    return first


def create_ncx_resources(
    mode: str,
    rows: list[tuple[str, str, str | None, str, str | None]],
) -> None:
    """Create NCX resources from CSV rows: one resource per row, type detected from value (IP/subnet or FQDN)."""
    api_keys = build_api_keys()
    token = api_keys.get("token") or os.environ.get("TOKEN") or os.environ.get("NCM_API_TOKEN")
    if not token:
        print("Error: TOKEN or NCM_API_TOKEN is required for NCX v3 API (set in API Keys tab).")
        return

    n2 = ncm.NcmClientv2(api_keys=api_keys, log_events=False)
    n3 = ncm.NcmClientv3(api_key=token, log_events=False)

    for identifier, ncx_network_id, site_name_override, resource_value, resource_name_override in rows:
        if mode == "router_id":
            routers = n2.get_routers(id__in=[identifier])
        else:
            routers = n2.get_routers(group=identifier, limit="all")

        if not routers:
            print(f"No routers found for {mode}={identifier!r}.")
            continue

        name = (resource_name_override or resource_value).strip()
        if len(name) < 3:
            print(
                f"Skipping resource {resource_value!r}: name must be at least 3 characters (use resource_name or a longer value)."
            )
            continue

        resource_type, extra_kwargs = classify_resource_target(resource_value.strip())

        for router in routers:
            print(
                f'Creating NCX resource {resource_value!r} for router {router["id"]} {router["name"]} '
                f"in network {ncx_network_id}..."
            )
            site = get_site(n3, router, site_name_override=site_name_override)
            if not site:
                continue

            try:
                resource = n3.create_exchange_resource(
                    site_id=site["id"],
                    resource_name=name,
                    resource_type=resource_type,
                    **extra_kwargs,
                )
            except Exception as e:
                print(
                    f"Error creating NCX resource {resource_value!r} for router {router['name']}: "
                    f"{type(e).__name__}: {e}"
                )
                continue
            if isinstance(resource, str):
                if "overlapping_resource" not in resource:
                    print(resource)
                continue
            if isinstance(resource, dict) and (resource.get("data") or resource.get("id")):
                # API returns JSON:API style: site has attributes.name, not top-level name
                site_name = (site.get("attributes") or {}).get("name") or site.get("name") or site.get("id") or "site"
                print(
                    f"Created NCX resource {resource_value!r} for router "
                    f'{router["name"]}, site {site_name}. (type={resource_type})'
                )
            else:
                print(
                    f"Error creating NCX resource {resource_value!r} for router {router['name']}. "
                    "Check subscriptions (router/site may need NCX license)."
                )
                if resource is not None:
                    print(f"  API response: {resource}")
        print()


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python "Create NCX Resources.py" <config_csv_path>')
        sys.exit(1)

    csv_filename = sys.argv[1]

    try:
        mode, rows = load_config_from_csv(csv_filename)
    except Exception as exc:
        print(f"Error reading configuration from CSV: {exc}")
        sys.exit(1)

    create_ncx_resources(mode, rows)


if __name__ == "__main__":
    main()

