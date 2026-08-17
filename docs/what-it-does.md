# FedEx Connector — what it actually does

FedEx is a shipping carrier: it doesn't sell or supply anything, it moves
packages for orders that already exist in Alaiy OS (ERPNext). This connector
gets rate quotes, creates/cancels shipments and labels, validates addresses,
looks up nearby FedEx locations, and pulls delivery status back onto the
**Delivery Note** that FedEx shipment belongs to.

---

## The short version

| | Direction | Automatic? |
|---|---|---|
| Rate quotes | Alaiy OS → FedEx | No — "Get FedEx Rates" button on a Delivery Note, on demand only |
| Address validation | Alaiy OS → FedEx | No — "Validate Address" button, on demand only |
| Locations search | Alaiy OS → FedEx | No — callable functions, no UI button wired yet |
| Shipment + label creation | Alaiy OS → FedEx | No — "Create FedEx Shipment" button on a Delivery Note |
| Shipment cancellation | Alaiy OS → FedEx | No — callable (`cancel_shipment`), no UI button wired yet |
| Delivery status | FedEx → Alaiy OS | Yes, if a Pull Sync Interval is set on Settings (Disabled by default) — otherwise only the manual "Refresh Tracking" button |
| Tracking number → Shopify | Alaiy OS → Shopify | Yes, automatically, immediately after a FedEx shipment is created — best-effort, only if the Shopify connector app is installed |

**Nothing writes to FedEx unless a button is clicked, or a scheduled sync
is explicitly turned on** (both Pull and Push intervals default to
`Disabled` on Settings). No shipment, label, rate quote, or address
validation call happens on its own just because a Delivery Note exists.

The one exception, once you do create a shipment through this connector:
the resulting tracking number is pushed to the linked Shopify order
automatically, in the same request — not something you need to trigger
separately. It's best-effort — if the Shopify connector isn't installed or
the push fails, the FedEx shipment (already created, already billed) is
not rolled back; the failure is only logged.

---

## Coming IN from FedEx

### Delivery status (Track API)
- **Scheduled poll** — if `Pull Sync Interval` on FedEx Connector Settings
  is anything other than `Disabled`, a background job runs on that cadence
  and refreshes `fedex_delivery_status` / `fedex_last_tracked_at` on every
  submitted Delivery Note that has a `fedex_tracking_number` and isn't
  already `DELIVERED`.
- **Manual** — the "Refresh Tracking" button on a Delivery Note runs the
  same lookup synchronously for that one DN.
- **Push (webhook)** — FedEx's Shipment Visibility Webhook would deliver
  the same status data in near-real time instead of polling. The receiver
  is built but disabled (`501` on every request) — see
  [webhooks.md](webhooks.md) for why.

## Going OUT to FedEx

### Rate quotes
"Get FedEx Rates" on a Delivery Note resolves the shipper (Default
Warehouse address), recipient (DN's shipping address), and weight (DN's
`total_net_weight`) and returns every FedEx service FedEx is willing to
quote, in FedEx's own order (not sorted by price).

### Address validation
"Validate Address" on a Delivery Note checks whether FedEx can resolve
the DN's shipping address to something deliverable. **Not wired as an
automatic gate before shipment creation** — it's a standalone check today.

### Locations search
Two functions (by address, by lat/long) return nearby FedEx drop-off/
pickup points. No Delivery Note button calls these yet — they're callable
from a report/console/future UI only.

### Shipment + label creation
"Create FedEx Shipment" on a Delivery Note creates a real FedEx shipment
(single package, drop-off only — no scheduled pickup), writes the tracking
number onto the DN, attaches the generated label PDF as a private file,
and pushes the tracking number to the linked Shopify order if that
connector is installed. Refuses to run again if the DN already has a
tracking number (cancel the existing shipment first).

### Shipment cancellation
`cancel_shipment()` calls FedEx's cancel endpoint. Callable, but no
Delivery Note button triggers it yet.
