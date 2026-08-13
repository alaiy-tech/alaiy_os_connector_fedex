# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
FedEx Locations Search API v1 (POST /location/v1/locations).

One endpoint, three search modes selected by locationSearchCriterion:
address, coordinates (LONGITUDE_AND_LATITUDE), or phone number.

FedEx's own developer portal page is JS-rendered and doesn't expose a
downloadable OpenAPI spec for this API -- schema here is the best publicly
surfaced shape (a virtual-sandbox mock's schema, cross-checked against
fedex.md's own summary of search inputs/filters/response fields), same
"verify live before trusting field names beyond what's confirmed" situation
as postal_code_validation.py and service_availability.py.
"""

import frappe

from alaiy_os_connector_fedex.fedex.client import FedexClient

SEARCH_PATH = "/location/v1/locations"


def search_locations_by_address(postal_code, country_code, city=None, state=None,
                                 location_types=None, radius_value=20, radius_units="MI",
                                 max_results=10):
    """Nearest FedEx drop-off/pickup points to a real address -- used for
    "nearest drop-off" (self-ship, returns) and Hold-at-Location options."""
    address = {"postalCode": postal_code or "", "countryCode": country_code or ""}
    if city:
        address["city"] = city
    if state:
        address["stateOrProvinceCode"] = state

    return _search({
        "location": {"address": address},
        "locationSearchCriterion": "ADDRESS",
        "locationTypes": location_types or [],
        "locationsSummaryRequestControlParameters": {
            "distance": {"units": radius_units, "value": radius_value},
            "maxResults": max_results,
        },
    })


def search_locations_by_coordinates(latitude, longitude, location_types=None,
                                     radius_value=20, radius_units="MI", max_results=10):
    """Same search, keyed by lat/long instead of a street address."""
    return _search({
        "location": {"longLat": {"latitude": latitude, "longitude": longitude}},
        "locationSearchCriterion": "LONGITUDE_AND_LATITUDE",
        "locationTypes": location_types or [],
        "locationsSummaryRequestControlParameters": {
            "distance": {"units": radius_units, "value": radius_value},
            "maxResults": max_results,
        },
    })


def _search(body):
    client = FedexClient()
    resp = client.post(SEARCH_PATH, json=body)
    output = resp.get("output") or {}
    return {
        "locations": output.get("locationDetailList") or [],
        "total_results": output.get("totalResults"),
        "results_returned": output.get("resultsReturned"),
        "alerts": output.get("alerts") or [],
    }
