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

- **Shipper** — `FedEx Connector Settings.fedex_default_warehouse`'s
  Address. Throws if not set.
- **Recipient** — the DN's `shipping_address_name`, falling back to
  `customer_address`. Throws if neither is set.
- **Weight** — the DN's `total_net_weight`. Throws if zero/unset.
- **Weight units** — the DN's `weight_uom`, mapped via
  `_weight_uom_to_fedex()`.

Wraps `FedexAPIError` into `frappe.throw()` so the button shows a real
user-facing message instead of a stack trace.

### `_weight_uom_to_fedex(weight_uom) -> "LB" | "KG"`

FedEx only accepts `LB` or `KG`. ERPNext's Weight UOM can be any real
unit (Gram, Ounce, Ton, ...). Recognized inputs: `kg`/`kilogram(s)` →
`KG`; `lb`/`lbs`/`pound(s)`/empty → `LB`. Anything else — `frappe.throw()`,
not a silent/wrong default, since silently mis-rating a shipment (e.g.
treating grams as pounds) is worse than failing loudly.

### `_erpnext_address_to_fedex(address_name) -> dict`

Shared with `address_validation.py` and `shipping.py`. Reads an ERPNext
`Address` doc and maps `address_line1/city/state/pincode/country` to
FedEx's field names, resolving `country` to its ISO 2-letter code via
`Country.code`.

## Settings required

| Field | Doctype | Required for |
|---|---|---|
| `fedex_account_number` | FedEx Connector Settings | Every Rate call |
| `fedex_default_warehouse` | FedEx Connector Settings | The button entry point's shipper resolution |
