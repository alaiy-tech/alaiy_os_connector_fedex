# Rate API

Module: `fedex/rating.py`. Endpoint: `POST /rate/v1/rates/quotes`.

## Request

```json
{
  "accountNumber": {"value": "740561073"},
  "requestedShipment": {
    "shipper": {
      "address": {
        "streetLines": ["1550 Union Meeting Rd"],
        "city": "Blue Bell",
        "stateOrProvinceCode": "PA",
        "postalCode": "19422",
        "countryCode": "US"
      }
    },
    "recipient": {
      "address": {
        "streetLines": ["10 Fedex Pkwy"],
        "city": "Memphis",
        "stateOrProvinceCode": "TN",
        "postalCode": "38125",
        "countryCode": "US"
      }
    },
    "pickupType": "DROPOFF_AT_FEDEX_LOCATION",
    "rateRequestType": ["LIST", "ACCOUNT"],
    "requestedPackageLineItems": [
      {"weight": {"value": 5, "units": "LB"}}
    ]
  }
}
```

`serviceType` is omitted by default — FedEx returns every eligible
service (a "LIST rate request"). Pass one (e.g. `"FEDEX_GROUND"`) to
restrict to a single service. `rateRequestType` defaults to
`["LIST", "ACCOUNT"]`; override via the `rate_request_type` param if you
only want one or the other.

Optional `dimensions` (`{length, width, height, units}`, units default
`"IN"`) get added into `requestedPackageLineItems[0].dimensions` — only
included at all if length/width/height are all truthy.

## Response

```json
{
  "output": {
    "rateReplyDetails": [
      {
        "serviceType": "FIRST_OVERNIGHT",
        "commit": { "...": "shape not yet confirmed, see below" },
        "ratedShipmentDetails": [
          {"totalNetCharge": 167.34, "currency": "USD"}
        ]
      },
      {"serviceType": "PRIORITY_OVERNIGHT", "...": "..."},
      {"serviceType": "STANDARD_OVERNIGHT", "...": "..."},
      {"serviceType": "FEDEX_2_DAY_AM", "...": "..."},
      {"serviceType": "FEDEX_2_DAY", "...": "..."},
      {"serviceType": "FEDEX_EXPRESS_SAVER", "...": "..."},
      {"serviceType": "FEDEX_GROUND", "...": "..."}
    ]
  }
}
```

Example quotes, cheapest to most expensive:

| Service | Total net charge |
|---|---|
| `FEDEX_GROUND` | $19.55 |
| `FEDEX_EXPRESS_SAVER` | $43.04 |
| `FEDEX_2_DAY` | $57.82 |
| `FEDEX_2_DAY_AM` | $69.74 |
| `STANDARD_OVERNIGHT` | $126.66 |
| `PRIORITY_OVERNIGHT` | $134.79 |
| `FIRST_OVERNIGHT` | $167.34 |

### `totalNetCharge` shape

`totalNetCharge` is a plain number (`167.34`), not the `{amount,
currency}` object the derived OpenAPI spec originally assumed —
`currency` is a sibling field on `ratedShipmentDetails[0]` instead.
`_parse_rate_reply()` handles both shapes:

```python
charge = rated[0].get("totalNetCharge")
if isinstance(charge, dict):
    amount, currency = charge.get("amount"), charge.get("currency")
else:
    amount, currency = charge, rated[0].get("currency")
```

### `transit_days`

`commit.transitDays` / `commit.commitMessageDetails` are both absent from
the response in practice, so `transit_days` is currently always `None`.
`commit`'s real field shape for transit time is not yet known.

## Functions

### `get_rate_quotes(shipper_address, recipient_address, weight_value, weight_units="LB", service_type=None, dimensions=None, rate_request_type=None) -> list[dict]`

`shipper_address` / `recipient_address`: `{address_line, city, state,
postal_code, country_code}`.

Returns `[{service_type, transit_days, total_net_charge, currency}, ...]`
in FedEx's own response order (not sorted by price). Raises
`RuntimeError` if `fedex_account_number` isn't set on Settings, or
`FedexAPIError` on any FedEx-side failure (invalid address, etc.).

### `get_rate_quotes_for_delivery_note(delivery_note) -> list[dict]`

Whitelisted entry point for a "Get FedEx Rates" button on a Delivery
Note. Resolves everything from real ERPNext data instead of requiring
re-entry:

- **Shipper** — `FedEx Connector Settings.fedex_default_warehouse`, a
  **Warehouse** (not an Address doctype — see `_warehouse_to_fedex()`
  below). Throws if not set, or if the warehouse has no
  `address_line_1`/`city`/`pin`.
- **Recipient** — the DN's `shipping_address_name`, falling back to
  `customer_address`. Throws if neither is set.
- **Weight** — the DN's `total_net_weight`. Throws if zero/unset.
- **Weight units** — the first Delivery Note item row that has a
  `weight_uom` set (the field lives per line item, not on the DN header),
  mapped via `_weight_uom_to_fedex()`.

Wraps `FedexAPIError` into `frappe.throw()` so the button shows a real
user-facing message instead of a stack trace.

### `_warehouse_to_fedex(warehouse_name, company) -> dict`

Shared with `shipping.py`. Reads the **Warehouse** doctype's own flat
address fields (`address_line_1`, `city`, `state`, `pin`, `phone_no`) —
`fedex_default_warehouse` is a Link to Warehouse, not Address; passing it
into `_erpnext_address_to_fedex()` raises "Address ... not found" outright.
Throws if the warehouse has no address set.

Country resolution prefers `Settings.fedex_shipper_country`; falls back to
the Company's registered country only if that's unset. Confirmed live
that defaulting to the Company's country unconditionally is wrong
whenever the warehouse ships from a different country — FedEx rejects
that with `ORIGIN.COUNTRY.NOTSERVED`.

### `_state_to_fedex_code(state, country_code) -> str`

Shared with `shipping.py`. FedEx's `stateOrProvinceCode` needs a 2-letter
code; ERPNext's Address/Warehouse state fields store whatever free-text
name a Country's state list uses (e.g. `"Tennessee"`) — confirmed live via
`SHIPPER.STATEORPROVINCECODE.INVALID` when passed through unconverted.
Only US states are mapped (`_US_STATE_CODES`, a fixed 50-state + DC
lookup) since that's the confirmed failure case; any other country's
state/province passes through unchanged.

### `_weight_uom_to_fedex(weight_uom) -> "LB" | "KG"`

FedEx only accepts `LB` or `KG`. ERPNext's Weight UOM can be any real
unit (Gram, Ounce, Ton, ...). Recognized inputs: `kg`/`kilogram(s)` →
`KG`; `lb`/`lbs`/`pound(s)`/empty → `LB`. Anything else — `frappe.throw()`,
not a silent/wrong default, since silently mis-rating a shipment (e.g.
treating grams as pounds) is worse than failing loudly.

### `_erpnext_address_to_fedex(address_name) -> dict`

Shared with `shipping.py` (not `address_validation.py` — that module reads
the Address doc's fields directly, without going through this helper or
its state-code conversion). Reads an ERPNext `Address` doc and maps
`address_line1/city/state/pincode/country/phone` to FedEx's field names,
resolving `country` to its ISO 2-letter code via `Country.code` and
`state` through `_state_to_fedex_code()`.

## Settings required

| Field | Doctype | Required for |
|---|---|---|
| `fedex_account_number` | FedEx Connector Settings | Every Rate call |
| `fedex_default_warehouse` | FedEx Connector Settings | The button entry point's shipper resolution (a Warehouse, not an Address) |
| `fedex_shipper_country` | FedEx Connector Settings | Preferred source of the shipper's country; falls back to the DN's Company's country if unset |
| `fedex_company` | FedEx Connector Settings | Shipper's `company_name` on the rate request |
