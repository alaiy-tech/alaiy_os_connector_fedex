# Address Validation API

Module: `fedex/address_validation.py`. Endpoint:
`POST /address/v1/addresses/resolve`.

## Request

```json
{
  "addressesToValidate": [
    {
      "address": {
        "streetLines": ["10 Fedex Pkwy"],
        "city": "Memphis",
        "stateOrProvinceCode": "TN",
        "postalCode": "38125",
        "countryCode": "US"
      }
    }
  ]
}
```

Only one address per call currently (`addressesToValidate` is a list in
the real API, capped at 100 per the spec, but `validate_address()` always
sends exactly one). No account number required for this API.

## Response

```json
{
  "output": {
    "resolvedAddresses": [
      {
        "streetLinesToken": ["10 FEDEX PKWY"],
        "city": "Memphis",
        "stateOrProvinceCode": "Región Metropolitana de Santiago",
        "postalCode": "38125",
        "countryCode": "CL",
        "classification": "UNKNOWN",
        "customerMessages": [],
        "attributes": {
          "ResolutionMethod": "GENERIC_VALIDATE",
          "MatchSource": "Postal",
          "CountrySupported": true,
          "ValidlyFormed": true,
          "Matched": true,
          "AddressType": "STANDARDIZED",
          "...": "many more attribute flags, all read as-is"
        }
      }
    ]
  }
}
```

### Sandbox geocoding caveat

FedEx's sandbox environment for this API returns canned/synthetic test
data unrelated to the real input (e.g. a US address's `countryCode` and
`stateOrProvinceCode` coming back set to unrelated foreign values) — this
is sandbox behavior, not a parsing bug. Sandbox validates the integration
path (auth, request shape, response parsing), not real-world geocoding
accuracy; judge address-validation accuracy only from production calls.

## Function

### `validate_address(address_line, city, state, postal_code, country_code) -> dict`

Returns:

```python
{
    "classification": "UNKNOWN",  # or RESIDENTIAL / BUSINESS / MIXED, per FedEx
    "resolved": {...},            # the full resolvedAddresses[0] dict, or None if FedEx returned nothing
    "is_deliverable": True,       # see below
    "messages": [],               # human-readable customerMessages text
}
```

`is_deliverable` is computed, not returned directly by FedEx — `False`
only if any `customerMessages[].code` is in
`{"UNDELIVERABLE", "MULTIPLE_MATCHES_FOUND", "INVALID"}`. Everything else
(a cosmetic standardization difference, a supported-but-unmatched address)
still counts as deliverable.

If `resolvedAddresses` is empty entirely, returns
`{"classification": "UNKNOWN", "resolved": None, "is_deliverable": False,
"messages": ["No resolvedAddresses in response."]}` — a design decision,
not a raised error: an empty resolution is a real business outcome (FedEx
found nothing), while a raised `FedexAPIError` is reserved for
request-level failures (auth, malformed request, FedEx downtime).

### `validate_delivery_note_address(delivery_note) -> dict`

Whitelisted entry point for a "Validate Address" button on a Delivery
Note. Reads the DN's `shipping_address_name` (falling back to
`customer_address`), resolves the Address doc's fields + ISO country
code, and calls `validate_address()`. Throws if the DN has no shipping
address at all.

## Where this fits in the shipping flow

Intended as a pre-check before `create_shipment_for_delivery_note` (see
`ship.md`) — validate the recipient address is real/deliverable before
spending an actual Ship API call (and, in production, real shipping cost)
on a bad address. **Not currently wired as an automatic gate** — it's a
standalone button today; `create_shipment_for_delivery_note` does not
call this first. Wiring that together is a real, small follow-up if
wanted.
