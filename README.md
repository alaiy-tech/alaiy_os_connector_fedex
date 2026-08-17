# Alaiy OS Connector: FedEx

FedEx carrier connector for Alaiy OS — shipment tracking, rating, address
validation, and label generation via the
[FedEx Ship/Track/Rate/Address Validation APIs](https://developer.fedex.com).
Unlike the marketplace connectors (Shopify, Flipkart, Amazon), FedEx isn't a
channel to sell through or a supplier to buy from — it moves shipments for
orders that already exist elsewhere in Alaiy OS.

## Status

| API | Status |
|---|---|
| Authorization (OAuth2) | Done |
| Track | Done |
| Rate | Done |
| Address Validation | Done |
| Ship (create + cancel + label) | Done |
| Shipment Visibility Webhook | Skeleton built, disabled |
| Pickup | Not built |

Full documentation — what it does, setup, architecture, and one page per
API (request/response bodies, function signatures, settings, known
field-shape gaps) — is in [`docs/`](docs/index.md).

## Auth

OAuth2 Client Credentials flow. FedEx splits Track into a separate
developer-portal project ("Basic Integrated Visibility") from
Ship/Rate/Address Validation — the two can't be combined into one
project. Details: [`docs/auth.md`](docs/auth.md).

## Error handling

`fedex/client.py` retries on `429`/`5xx` honoring FedEx's `Retry-After`
header, and raises `FedexAPIError` with FedEx's real error code/message
instead of a generic `requests.HTTPError`. Details: [`docs/auth.md`](docs/auth.md#error-handling).

## Schema documentation

FedEx does not provide a downloadable OpenAPI spec for Ship, Rate, or
Address Validation without portal login (Track + Authorization were
obtained this way — see `fedex/openapi/fedex-track-api-openapi.yml`'s
header). The Ship/Rate/Address Validation specs in that same directory
are derived from the stable v1 field shapes used across FedEx's own SDKs
and public integration guides, marked as such in each file's header.
Response handling reads fields defensively (permissive schema) rather
than assuming a strict shape.

## Prerequisites

- A Frappe v16 / ERPNext v16 bench with `alaiy_os` already installed.
- A FedEx Developer Portal project with Ship + Rate + Address Validation
  APIs selected, plus a separate "Basic Integrated Visibility" project
  for Track (see [Auth](#auth)).
- A Sandbox Test Account number from that project (separate from a
  production account number) for initial testing.

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app alaiy_os_connector_fedex /path/to/this/repo
bench install-app alaiy_os_connector_fedex
bench --site <site> migrate
bench build --app alaiy_os_connector_fedex
```

Then, on **FedEx Connector Settings**: set Client ID, Client Secret,
Account Number, and toggle Sandbox on for initial testing.

## File reference

| Path | Role |
|---|---|
| `hooks.py` | App manifest, install/migrate hooks, sidebar log registration, scheduler cron. |
| `connector_meta.py` | Registration row for `OS Connector Registry`. |
| `fedex/client.py` | `FedexClient` / `FedexAPIError` — OAuth2 token fetch/cache, retry-on-429/5xx, `get`/`post` helpers. |
| `fedex/tracking.py` | Track API — pull shipment status onto Delivery Notes. |
| `fedex/rating.py` | Rate API — rate quotes and transit times. |
| `fedex/address_validation.py` | Address Validation API. |
| `fedex/shipping.py` | Ship API — create/cancel shipments, label generation. |
| `fedex/webhooks.py` | Shipment Visibility Webhook receiver — disabled, see `docs/webhooks.md`. |
| `fedex/sync.py` | Sync Log lifecycle helpers; `run_pull_sync` delegates to tracking, `run_push_sync` stays a no-op (Ship is on-demand per-DN, not a batch sync). |
| `fedex/sync_jobs.py` | Scheduler entry point — decides what's due and enqueues it. |
| `api/test_connection.py` | Whitelisted reachability check (real OAuth exchange). |
| `api/sync.py` | Whitelisted trigger/status endpoints for the connector card, settings form, and manual tracking refresh. |
| `alaiy_os_connector_fedex/doctype/fedex_connector_settings/` | Single DocType: Client ID/Secret/Account Number, sandbox toggle, cached token, ERPNext defaults, sync intervals. |
| `alaiy_os_connector_fedex/doctype/fedex_sync_log/` | One row per sync run. |
| `docs/*.md` | Full documentation per API. |
| `fedex/openapi/*.yml` (docs repo) | Schema reference for every API — see [Schema documentation](#schema-documentation) for what's official vs. derived. |

## Contributing

```bash
cd apps/alaiy_os_connector_fedex
pre-commit install
```

## License

AGPL-3.0 (`license.txt`).
