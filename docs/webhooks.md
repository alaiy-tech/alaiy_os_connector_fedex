# Shipment Visibility Webhook

**Status: NOT LIVE.** Receiver skeleton built (event routing + Delivery
Note update logic fully written), but the actual HTTP endpoint is
deliberately disabled and returns `501 Not Implemented` for every request.

Module: `fedex/webhooks.py`. Target API: FedEx's Shipment Visibility
Webhook (`svm/v1`) — pushes near-real-time tracking events to a
registered HTTPS endpoint, replacing the need to poll Track API.

## Why this is disabled, not just incomplete

FedEx's subscription request/response shape and payload **signing
scheme** for this webhook are not documented anywhere accessible to this
repo:

- No cached OpenAPI spec exists for it (unlike Track/Authorization, which
  were real portal exports — see `fedex-track-api-openapi.yml`'s header).
- The `docs.fedex.com` page for this API is JS-rendered with no
  downloadable schema visible without portal login (same class of gap
  Ship/Rate had — those were solved by deriving a schema from
  well-established stable field shapes; this webhook's *security*
  mechanism has no equivalent "well-established public shape" to derive
  from safely).

Shipping an unauthenticated `allow_guest=True` endpoint that accepts
arbitrary tracking-status payloads and writes them onto Delivery Notes is
a real security hole — anyone who found the URL could push fake
"DELIVERED" statuses (or worse, once this expands) onto real orders. That
is not an acceptable placeholder to leave "open for now" the way a
missing feature normally would be. `verify_signature()` always returns
`False`, and `receive_notification()` hard-guards on `501` *before*
touching `verify_signature()` at all — even if signature verification
were accidentally bypassed downstream, the endpoint still refuses.

## What's already built (ready to activate)

### `_handle_tracking_event(payload)`

Parses a tracking-event payload permissively — same posture as
`tracking.py`'s poll path, since FedEx's own docs describe the *poll*
response shape as intentionally permissive and the webhook payload is
assumed (not confirmed) to carry an equivalent shape:

```python
tracking_number = (
    (payload.get("trackingNumberInfo") or {}).get("trackingNumber")
    or payload.get("trackingNumber")
)
```

Looks up the Delivery Note by `fedex_tracking_number`, and if found,
writes `fedex_delivery_status` / `fedex_last_tracked_at` — the exact same
fields the Track poll writes, using the exact same `_extract_status()`
helper. If no matching DN exists yet (notification arrived before the
Ship API call that set the tracking number, or for a tracking number this
system never created), it's logged as `"skipped"`, not an error.

### `_log_event(event_type, trigger_status, payload)`

Writes a `FedEx Sync Log` row per event (`sync_type="track_pull"`,
`trigger="webhook"`) — every webhook call is auditable in the same log
table the scheduled poll uses, whether or not it resulted in a DN update.

### `verify_signature(request)`

Stub. **Always returns `False`.** Exists so the shape is ready to fill
in — once FedEx's real signing convention is known, this is the only
function that needs real logic.

### `receive_notification()`

The actual whitelisted, guest-accessible endpoint. Currently:

```python
@frappe.whitelist(allow_guest=True)
def receive_notification():
    frappe.local.response.http_status_code = 501
    return {"error": "FedEx webhook receiver not yet implemented -- signing scheme undocumented."}
```

Every request gets `501`, unconditionally — the event-handling logic
above is never reached from this entry point today.

## To complete this

1. Get the real subscription request/response shape and signing-header
   convention from FedEx — export the `svm/v1` OpenAPI spec from the dev
   portal if one becomes downloadable, or get it from FedEx support/docs
   directly. Save it to `fedex/openapi/`, same convention as every other
   API here.
2. Implement `verify_signature(request)` against that real scheme
   (likely an HMAC signature header, or possibly IP-allowlist-based —
   unknown until the spec is in hand).
3. Remove the `501` guard in `receive_notification()`, wire it to call
   `verify_signature()` and route by `eventType` into
   `_handle_tracking_event()` (or a richer handler, if the real payload
   carries more than tracking status).
4. Add a `subscribe_webhook()` function to actually register this
   endpoint's URL with FedEx, once the subscription request shape is
   known — there's currently no code that tells FedEx this URL exists at
   all.

## Relationship to Track API

This webhook is the *push* counterpart to `track.md`'s *poll* mechanism —
same underlying tracking-status data, delivered a different way. Track's
polling loop keeps working regardless of whether this webhook ever gets
activated; this is a latency/efficiency improvement (real-time instead of
periodic polling), not a required replacement.
