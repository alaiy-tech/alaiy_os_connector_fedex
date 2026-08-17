# Locations Search API

Module: `fedex/locations_search.py`. Endpoint: `POST /location/v1/locations`.
One endpoint, three search modes selected by `locationSearchCriterion` —
this connector implements two of them (address, coordinates); phone-number
search is not implemented.

Not documented in a downloadable OpenAPI spec — FedEx's developer portal
page for this API is JS-rendered with no spec exposed without portal
login. The request/response shape here is the best publicly surfaced
shape available (a virtual-sandbox mock's schema, cross-checked against
FedEx's own summary of search inputs/filters/response fields) — same
"verify live before trusting field names beyond what's confirmed" posture
as the rest of this connector's less-documented APIs.

## Request

```json
{
  "location": {"address": {"postalCode": "38125", "countryCode": "US", "city": "Memphis", "stateOrProvinceCode": "TN"}},
  "locationSearchCriterion": "ADDRESS",
  "locationTypes": [],
  "locationsSummaryRequestControlParameters": {
    "distance": {"units": "MI", "value": 20},
    "maxResults": 10
  }
}
```

Coordinate search sends `{"location": {"longLat": {"latitude": ..., "longitude": ...}}, "locationSearchCriterion": "LONGITUDE_AND_LATITUDE"}` instead.

## Response

```json
{
  "output": {
    "locationDetailList": [{"...": "location details, read as-is"}],
    "totalResults": 3,
    "resultsReturned": 3,
    "alerts": []
  }
}
```

## Functions

### `search_locations_by_address(postal_code, country_code, city=None, state=None, location_types=None, radius_value=20, radius_units="MI", max_results=10) -> dict`

Nearest FedEx drop-off/pickup points to a real address — intended for
"nearest drop-off" (self-ship, returns) and Hold-at-Location options.
Returns `{locations, total_results, results_returned, alerts}`.

### `search_locations_by_coordinates(latitude, longitude, location_types=None, radius_value=20, radius_units="MI", max_results=10) -> dict`

Same search, keyed by lat/long instead of a street address. Same return
shape.

No account number is required for this API (matches Address Validation,
unlike Rate/Ship).

## Not built

- No UI entry point — both functions are callable but nothing on a
  Delivery Note or elsewhere calls them yet.
- Phone-number search mode (the third `locationSearchCriterion` FedEx
  supports) is not implemented.
- Response field names are not confirmed against a real FedEx call (see
  the module docstring's caveat above) — treat `locationDetailList`'s
  exact shape as provisional until verified live.
