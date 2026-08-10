# Ship API

Module: `fedex/shipping.py`. Endpoints:
`POST /ship/v1/shipments`, `PUT /ship/v1/shipments/cancel`.

## Request

```json
{
  "accountNumber": {"value": "740561073"},
  "labelResponseOptions": "LABEL",
  "requestedShipment": {
    "shipper": {
      "contact": {"personName": "Test Shipper", "phoneNumber": "9015551234", "companyName": "Alaiy Test"},
      "address": {"streetLines": ["1550 Union Meeting Rd"], "city": "Blue Bell", "stateOrProvinceCode": "PA", "postalCode": "19422", "countryCode": "US"}
    },
    "recipients": [
      {
        "contact": {"personName": "Test Recipient", "phoneNumber": "9015555678", "companyName": "FedEx"},
        "address": {"streetLines": ["10 Fedex Pkwy"], "city": "Memphis", "stateOrProvinceCode": "TN", "postalCode": "38125", "countryCode": "US"}
      }
    ],
    "pickupType": "DROPOFF_AT_FEDEX_LOCATION",
    "serviceType": "FEDEX_GROUND",
    "packagingType": "YOUR_PACKAGING",
    "shippingChargesPayment": {"paymentType": "SENDER"},
    "labelSpecification": {"imageType": "PDF", "labelStockType": "PAPER_85X11_TOP_HALF_LABEL"},
    "requestedPackageLineItems": [
      {"weight": {"value": 5, "units": "LB"}}
    ]
  }
}
```

`shippingChargesPayment.paymentType` is hardcoded to `"SENDER"` — no
third-party/recipient billing support built. `pickupType` is hardcoded to
`"DROPOFF_AT_FEDEX_LOCATION"` — no scheduled-pickup integration (would
need the Pickup API, not built).

If `reference` is passed to `create_shipment()`, it's attached as
`requestedPackageLineItems[0].customerReferences[0]` with type
`CUSTOMER_REFERENCE`, truncated to 40 chars.

## Response

```json
{
  "output": {
    "transactionShipments": [
      {
        "masterTrackingNumber": "794850511721",
        "pieceResponses": [
          {
            "packageDocuments": [
              {"encodedLabel": "JVBERi0xLjQKMSAwIG9iag..."}
            ]
          }
        ]
      }
    ]
  }
}
```

`encodedLabel` is base64-encoded; decoded bytes start with the literal
`%PDF-1.4` header for the default `PDF` label format.

## Functions

### `create_shipment(shipper, recipient, service_type, weight_value, weight_units="LB", packaging_type="YOUR_PACKAGING", dimensions=None, reference=None) -> dict`

Generic — no dependency on any ERPNext doctype, callable from any context
(not just Delivery Note). `shipper`/`recipient`:
`{contact_name, phone, company_name, address_line, city, state,
postal_code, country_code}`.

Returns:

```python
{
    "tracking_number": "794850511721",
    "label_bytes": b"%PDF-1.4\n...",   # decoded, ready to write to a file
    "label_content_type": "PDF",
}
```

Raises `RuntimeError` if `fedex_account_number` isn't set. Raises
`FedexAPIError` if:

- FedEx returns no `transactionShipments` at all (accepted the request but
  gave back nothing usable — the raw response is included in the error
  message for debugging).
- The one shipment returned has no `masterTrackingNumber`.

`label_bytes` is `None` (not an error) if FedEx returned a shipment with
no `encodedLabel` — that's a valid outcome when `labelResponseOptions` is
set to `URL_ONLY` instead of `LABEL` (not currently used — this module
always requests `LABEL`).

### `cancel_shipment(tracking_number)`

Calls the cancel endpoint. No return value; raises `FedexAPIError` on
failure the same way every other call does. **Not yet wired to any UI
button** — callable but no entry point built.

### `create_shipment_for_delivery_note(delivery_note, service_type) -> dict`

Whitelisted entry point for a "Create FedEx Shipment" button on a
Delivery Note. Resolves everything from real ERPNext data:

- **Refuses to run if the DN already has a `fedex_tracking_number`** —
  throws telling the user to cancel the existing shipment first. Prevents
  accidentally double-shipping the same DN.
- **Shipper** — `FedEx Connector Settings.fedex_default_warehouse`'s
  Address, with `company_name` from `Settings.fedex_company`. Throws if
  the warehouse isn't set.
- **Recipient** — DN's `shipping_address_name` (falling back to
  `customer_address`), with `contact_name` from `dn.contact_person` or
  `dn.customer_name`, and `company_name` from `dn.customer_name`. Throws
  if no shipping address exists.
- **Weight** — DN's `total_net_weight` + `weight_uom` (via
  `rating.py`'s `_weight_uom_to_fedex`). Throws if zero/unset.
- Passes `dn.name` as the shipment `reference`.

On success:

1. Writes `fedex_tracking_number` onto the DN.
2. If a label came back, saves it as a real **private** File
   (`{dn.name}-fedex-label.pdf`) attached to the Delivery Note via
   `frappe.utils.file_manager.save_file`, and writes the file's URL onto
   the new `fedex_label` (Attach field) custom field.
3. Commits.

Returns `{"tracking_number": "..."}`. A `FedexAPIError` from
`create_shipment()` is caught and re-raised via `frappe.throw()` — a
real user-facing message, not a stack trace.

## Fields written

On **Delivery Note**:

| Field | Type | Written by |
|---|---|---|
| `fedex_tracking_number` | Data | This module (or manually) |
| `fedex_label` | Attach, read-only | This module only |

## Defaults / not configurable yet

- `_DEFAULT_LABEL_IMAGE_TYPE = "PDF"`, `_DEFAULT_LABEL_STOCK_TYPE =
  "PAPER_85X11_TOP_HALF_LABEL"` — hardcoded module constants, not exposed
  on Settings. A site with a thermal printer would need these changed in
  code (e.g. to `"ZPLII"` / a thermal stock type), not via the UI.
- `packagingType` defaults to `"YOUR_PACKAGING"` — no FedEx-branded box
  support wired.
- Only single-package shipments — `requestedPackageLineItems` always has
  exactly one entry. Multi-package shipments aren't supported.

## Not built

- Address Validation is **not** automatically called before shipment
  creation — see `address_validation.md`'s note on this. A bad address
  will fail at the Ship API call itself (a real `FedexAPIError`), not be
  caught earlier.
- No UI entry point for `cancel_shipment` yet.
- No Pickup API integration — `pickupType` is always drop-off.
