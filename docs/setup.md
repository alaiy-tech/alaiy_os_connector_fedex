# Setup & Configuration

Standalone Frappe app (`alaiy_os_connector_fedex`) that registers itself
into Alaiy OS's Connector Registry. It ships **disabled**
(`is_enabled = 0` by default on `FedEx Connector Settings`). Enabling it
provisions custom fields on Delivery Note — nothing more (no webhooks to
register, since the webhook receiver is disabled; no price lists or
suppliers, since FedEx is a carrier, not a marketplace).

---

## 1. Prerequisites

- Frappe bench with `alaiy_os` and `erpnext` installed (`required_apps` in
  `hooks.py`).
- A FedEx Developer Portal project with **Ship, Rate & other APIs**
  selected (covers Ship, Rate, Address Validation, Locations Search) —
  create a project at https://developer.fedex.com.
- If you also want Track, a **separate** "Basic Integrated Visibility"
  project — FedEx does not let Track share a project with Ship/Rate. Each
  project has its own Client ID/Secret, and only one pair fits on Settings
  at a time (it's a Single doctype).
- For sandbox testing, the project's **Sandbox Test Account** number
  (auto-generated on the dev portal) — not a real production account
  number.

## 2. FedEx credentials → Settings fields

| FedEx-side value | Settings field | Notes |
|---|---|---|
| Client ID (API Key) | `fedex_client_id` | Pasted directly, not minted by the connector |
| Client Secret | `fedex_client_secret` | Pasted directly (Password field) |
| Sandbox Test Account number, or your real account number | `fedex_account_number` | Required by every Rate/Ship call |

The connector mints its own **access token** via the OAuth2
client-credentials exchange (`fedex_access_token` /
`fedex_token_expires_at`) — you never paste an access token yourself; see
[auth.md](auth.md).

## 3. FedEx Connector Settings — every field

Grouped exactly as the DocType JSON groups them
(`fedex_connector_settings.json`):

**API Connection**

| Field | Type | Purpose |
|---|---|---|
| `is_enabled` | Check | Master on/off switch. Flipping 0→1 runs first-enable setup (see below). |
| `fedex_use_sandbox` | Check, default on | Sandbox (`apis-sandbox.fedex.com`) vs production (`apis.fedex.com`) base URL. |
| `fedex_client_id` | Data, required | OAuth2 client_id. |
| `fedex_client_secret` | Password, required | OAuth2 client_secret. |
| `fedex_access_token` | Password, read-only | Cached access token — set by the connector, not you. |
| `fedex_token_expires_at` | Datetime, read-only | When the cached token needs refreshing — set by the connector. |

**Alaiy OS Defaults**

| Field | Type | Purpose |
|---|---|---|
| `fedex_company` | Link → Company | Used as `company_name` on the shipper when creating a shipment. |
| `fedex_default_warehouse` | Link → **Warehouse** | Ship-from location for rate quotes and shipment creation — read from the Warehouse's own address fields (`address_line_1`, `city`, `state`, `pin`, `phone_no`), not a linked Address doctype. |
| `fedex_shipper_country` | Link → Country | Country of that warehouse's real ship-from address. Preferred over the Company's registered country (which can be a different country than where the warehouse actually ships from — FedEx will reject the request with `ORIGIN.COUNTRY.NOTSERVED` if it's wrong). Falls back to the Company's country only if this is unset. |
| `fedex_account_number` | Data | Billing account number for every Rate/Ship call. |

The DocType JSON's own field descriptions for `fedex_company`,
`fedex_default_warehouse`, and `fedex_account_number` still say "not read
by any sync logic yet" / "placeholder for when it is" — that text predates
Rate/Ship being built and is stale; all three fields are read by
`fedex/rating.py` and `fedex/shipping.py` today. Worth fixing in the
DocType JSON itself, independent of this docs pass.

**Sync Schedule**

| Field | Type | Purpose |
|---|---|---|
| `fedex_pull_sync_interval` | Select, default `Disabled` | How often the scheduled Track poll runs (`5/15/30/60 min`, or `Disabled`). |
| `fedex_push_sync_interval` | Select, default `Disabled`, marked required | How often a push sync would run. Currently has nothing to do — see [architecture.md](architecture.md#change-detection--identity). |

## 4. First enable

The Settings doctype controller (`fedex_connector_settings.py`) detects the
`is_enabled` `0 → 1` transition in `validate()` and runs `_on_first_enable()`
from `on_update()`:

- Calls `setup/install.py`'s `setup_custom_fields()`, which idempotently
  adds four custom fields to **Delivery Note**: `fedex_tracking_number`,
  `fedex_delivery_status` (read-only), `fedex_last_tracked_at` (read-only),
  `fedex_label` (read-only Attach).
- Nothing else — no webhook registration (the webhook is disabled), no
  price lists, no suppliers.

Installing and migrating the app **without** enabling it does not create
these fields — `bench migrate` alone only registers the connector in the
OS Connector Registry and forces the Settings doctype to Single
(`sync_connector_registry()`); the Delivery Note fields only appear once
someone flips `is_enabled` on and saves.

Disabling (`1 → 0`) runs `_on_disable()`, which today does nothing (no
webhook to unregister).

Changing `fedex_client_id` or `fedex_client_secret` on an existing,
already-saved Settings doc clears the cached `fedex_access_token` /
`fedex_token_expires_at` automatically, so a credential rotation never
leaves a request running on a token minted under the old credentials.
