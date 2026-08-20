# Architecture & Sync Engine

The plumbing shared across every domain: auth, the API client, install/
enable lifecycle, scheduling, and log visibility.

---

## Connector pattern

Standalone Frappe app, registers into Alaiy OS's Connector Registry on
every `bench migrate` (`hooks.py: after_migrate` →
`setup/install.py:sync_connector_registry()`, idempotent). Settings live on
a Single doctype (`FedEx Connector Settings`), driven by
`connector_meta.py`'s static metadata (connector id/name/icon, which
method the "Test Connection" button calls, which methods the two sync
"slots" call). Sync history is visible in the `FedEx Sync Log` doctype,
surfaced under Alaiy OS's sidebar via `alaiy_os_sidebar_log_items` in
`hooks.py`.

FedEx doesn't fit either of the registry's two connector-type buckets
("channel" to sell through, "supplier" to buy from) — it's registered as
`connector_type: "channel"` as the closest existing option, pending a real
"carrier" type in the registry.

## Auth & client

`fedex/client.py`'s `FedexClient` does the OAuth2 client-credentials
exchange (`POST {base_url}/oauth/token`, form-encoded
`grant_type=client_credentials&client_id=...&client_secret=...`). See
[auth.md](auth.md) for the full request/response shape and token caching.

Every real API call (`get`/`post`/`put`) retries up to 3 times on
`429/500/502/503/504`, honoring the response's `Retry-After` header
(falls back to `2 * (attempt + 1)` seconds if absent). On terminal
failure it raises `FedexAPIError(message, status_code, fedex_errors,
retryable)` built from FedEx's own `{"errors": [{"code", "message"}]}`
body — never a bare `requests.HTTPError`. All requests use a 30s timeout.

## Change detection & identity

There is no de-duplication logic in this connector, and by design: every
outbound call (rate quote, shipment, address validation, locations
search) is triggered by an explicit button click on a specific Delivery
Note, not a batch sync scanning for "what changed." The one guard that
exists is `create_shipment_for_delivery_note` refusing to run again if the
Delivery Note already has a `fedex_tracking_number` — that's a
double-shipment guard, not change detection.

`fedex/sync.py:run_push_sync` is a no-op stub kept only so the scheduler
wiring every Alaiy OS connector is expected to have has something to
point at — Ship is a real, on-demand action, not a thing to push on a
schedule. `Push Sync Interval` on Settings currently has no effect.

## Sync log / error visibility

`FedEx Sync Log` (`sync_type`, `trigger`, `status`, `started_at`/
`finished_at`, `items_processed`/`items_updated`/`items_failed`,
`error_message`) is written by `fedex/sync.py`'s `get_or_create_log` /
`_mark_running` / `_mark_finished` helpers, shared by the Track poll and
the webhook receiver's event logging. A scheduled Track poll updates the
log's counters after every batch of 30 tracking numbers, not just at the
end, so a long-running poll is inspectable mid-run. Any unhandled
exception during a sync is also written to the Frappe Error Log via
`frappe.log_error`.

## Scheduler

`hooks.py` runs `fedex/sync_jobs.py:check_and_enqueue()` every minute via
`scheduler_events`. It only enqueues a real job when: the connector is
enabled, the configured interval (`fedex_pull_sync_interval` /
`fedex_push_sync_interval`) isn't `Disabled`, no non-stale job for that
sync type is already running (a job "running" for over 30 minutes is
treated as dead), and the last successful run is older than the
configured interval.
