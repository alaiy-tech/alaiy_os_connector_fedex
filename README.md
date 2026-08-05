# Alaiy OS Connector: FedEx

FedEx carrier connector for Alaiy OS — shipment tracking, rating, and label
generation via the [FedEx Ship/Track/Rate APIs](https://developer.fedex.com).
Unlike the marketplace connectors (Shopify, Flipkart, Amazon), FedEx isn't a
channel to sell through or a supplier to buy from — it moves shipments for
orders that already exist elsewhere in Alaiy OS.

## Status

Authentication only, so far. Nothing beyond OAuth2 + a reachability check is
implemented yet — no shipment creation, tracking pull, or rating.

## Auth

OAuth2 Client Credentials flow, confirmed against
`fedex/openapi/fedex-authorization-api-openapi.yml`:

```
POST {base_url}/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=<Client ID>&client_secret=<Client Secret>
```

Returns a bearer token, documented as 1-hour lived — cached on **FedEx
Connector Settings** (`fedex_access_token` / `fedex_token_expires_at`) and
refreshed automatically before it expires, same pattern as the other
connectors' clients. Base URL toggles between `apis.fedex.com` (production)
and `apis-sandbox.fedex.com` (sandbox) via the settings form.

FedEx has no generic `/ping` endpoint, so `test_connection()` performs the
real OAuth exchange rather than hitting a placeholder URL.

## Prerequisites

- A Frappe v16 / ERPNext v16 bench with `alaiy_os` already installed.
- FedEx Developer Portal Client ID + Client Secret.

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app alaiy_os_connector_fedex /path/to/this/repo
bench install-app alaiy_os_connector_fedex
bench --site <site> migrate
bench build --app alaiy_os_connector_fedex
```

## File reference

| Path | Role |
|---|---|
| `hooks.py` | App manifest, install/migrate hooks, sidebar log registration, scheduler cron. |
| `connector_meta.py` | Registration row for `OS Connector Registry`. |
| `fedex/client.py` | `FedexClient` — OAuth2 token fetch/cache + `get`/`post` helpers. |
| `fedex/sync.py` | Sync Log lifecycle helpers; `run_pull_sync`/`run_push_sync` are still stubs. |
| `fedex/sync_jobs.py` | Scheduler entry point — decides what's due and enqueues it. |
| `api/test_connection.py` | Whitelisted reachability check (real OAuth exchange). |
| `api/sync.py` | Whitelisted trigger/status endpoints for the connector card and settings form. |
| `alaiy_os_connector_fedex/doctype/fedex_connector_settings/` | Single DocType: Client ID/Secret, sandbox toggle, cached token, ERPNext defaults, sync intervals. |
| `alaiy_os_connector_fedex/doctype/fedex_sync_log/` | One row per sync run. |

## Contributing

```bash
cd apps/alaiy_os_connector_fedex
pre-commit install
```

## License

AGPL-3.0 (`license.txt`).
