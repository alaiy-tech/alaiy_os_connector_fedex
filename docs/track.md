# Track API

Module: `fedex/tracking.py`. Endpoint: `POST /track/v1/trackingnumbers`.

## Request

```json
{
  "includeDetailedScans": false,
  "trackingInfo": [
    {"trackingNumberInfo": {"trackingNumber": "794850511721"}},
    {"trackingNumberInfo": {"trackingNumber": "..."}}
  ]
}
```

`trackingInfo` is capped at **30 entries per request** — FedEx's own
documented `maxItems`. `_chunk()` splits any larger list into batches of
30 before calling the API.

## Response

```json
{
  "output": {
    "completeTrackResults": [
      {
        "trackingNumber": "794850511721",
        "trackResults": [
          {
            "latestStatusDetail": {
              "description": "In transit",
              "statusByLocale": "In transit",
              "code": "IT"
            },
            "...": "everything else is permissive, see below"
          }
        ]
      }
    ]
  }
}
```

FedEx's own docs describe `trackResults[]`'s schema as intentionally
permissive (`additionalProperties: true`, "consult the FedEx Developer
Portal for full payload field definitions") — there is no fixed shape to
validate against. `_extract_status()` reads it defensively:

```python
def _extract_status(track_result):
    latest = track_result.get("latestStatusDetail") or {}
    return (
        latest.get("description")
        or latest.get("statusByLocale")
        or latest.get("code")
        or None
    )
```

Tries `description` first, falls back to `statusByLocale`, then `code`,
then gives up and returns `None` (written as `"UNKNOWN"` by the caller) —
never raises on an unexpected shape.

## Functions

### `track_shipments(tracking_numbers: list[str]) -> dict[str, dict | None]`

Direct call, no Sync Log. Used for a single Delivery Note's manual
"Refresh Tracking" action. Returns `{tracking_number: track_result_or_None}`
— one entry per input number, `None` if FedEx returned nothing for it.

Batches internally at 30/request; if you pass 45 numbers, it makes 2 API
calls and merges the results into one dict.

### `track_pending_deliveries(trigger="scheduled", log_name=None) -> dict`

The scheduled poll. Queries every **submitted** (`docstatus=1`) Delivery
Note where `fedex_tracking_number` is set and `fedex_delivery_status` is
not already `"DELIVERED"`. For each batch of 30:

1. Calls `track_shipments()`.
2. On a whole-batch exception (network error, etc.) — logs it, marks every
   DN in that batch as failed, and **continues to the next batch** rather
   than aborting the whole run.
3. Per DN: if no result came back, counts as failed. Otherwise writes
   `fedex_delivery_status` (truncated to 140 chars) and
   `fedex_last_tracked_at` via `frappe.db.set_value`.
4. Commits and updates the Sync Log's `items_processed`/`items_updated`/
   `items_failed` after every batch (not just at the end) — a long-running
   poll is inspectable mid-run, not a black box until it finishes.

Returns `{"processed": N, "updated": N, "failed": N}`. Final Sync Log
status is `"success"` only if `failed == 0`; otherwise `"failed"` with an
`error_message` pointing at the Error Log for details.

## Entry points wired to the UI

- `api/sync.py:refresh_delivery_note_tracking(delivery_note)` — the
  manual "Refresh Tracking" button on a Delivery Note. Synchronous (a
  single tracking number is one fast API call — no reason to queue it).
- `fedex/sync.py:run_pull_sync(trigger, log_name)` — thin wrapper calling
  `track_pending_deliveries`; this is what the scheduler and
  `api/sync.py:trigger_pull_sync()` (manual "Sync Now" button) both call
  into.

## Fields written

On **Delivery Note** (custom fields from `setup/install.py`):

| Field | Type | Written by |
|---|---|---|
| `fedex_tracking_number` | Data | Manually entered, or by `create_shipment_for_delivery_note` (see `ship.md`) |
| `fedex_delivery_status` | Data, read-only | This module |
| `fedex_last_tracked_at` | Datetime, read-only | This module |

## Not built

- No inbound webhook here — Track API's own `/track/v1/notifications`
  endpoint is *outbound* (asks FedEx to send **email** notifications), not
  a receiver for push updates. Polling is the only pull mechanism. See
  `webhooks.md` for the separate Shipment Visibility Webhook, which *is*
  the real push mechanism — currently disabled pending its spec.
