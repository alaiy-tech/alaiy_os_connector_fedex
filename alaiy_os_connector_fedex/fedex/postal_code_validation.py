# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Postal code validation via FedEx Postal Code Validation API v1
(POST /postal/v1/validate).

FedEx has not published a downloadable spec for this API (same situation
as rating.py) -- schema derived from fedex.md's own summary (carrierCode,
countryCode, stateOrProvinceCode, postalCode, shipDate in; cleanedPostalCode,
locationDetails out) and the stable v1 request/response shape shared across
FedEx's other v1 APIs. Verify against a real sandbox response before relying
on field names beyond what's documented in fedex.md.
"""

import frappe

from alaiy_os_connector_fedex.fedex.client import FedexClient

VALIDATE_PATH = "/postal/v1/validate"


def validate_postal_code(country_code, postal_code, state=None, ship_date=None, carrier_code="FDXG"):
    """Validates a postal/state/country combination independent of a full
    street address. Per fedex.md: postal alignment and territory alignment
    are separate outputs -- do not cross-reference them.

    state is required for US/CA/MX per the spec; non-postal-aware countries
    can pass a placeholder postal_code (FedEx documents "00000" for these).

    Returns {is_valid, cleaned_postal_code, location_details, raw}.
    Raises FedexAPIError via FedexClient on a request-level failure.
    """
    client = FedexClient()
    body = {
        "carrierCode": carrier_code,
        "countryCode": country_code or "",
        "postalCode": postal_code or "",
    }
    if state:
        body["stateOrProvinceCode"] = state
    if ship_date:
        body["shipDate"] = ship_date

    resp = client.post(VALIDATE_PATH, json=body)
    output = resp.get("output") or {}

    return {
        "is_valid": bool(output.get("cleanedPostalCode") or output.get("locationDetails")),
        "cleaned_postal_code": output.get("cleanedPostalCode"),
        "location_details": output.get("locationDetails"),
        "raw": output,
    }


@frappe.whitelist()
def validate_delivery_note_postal_code(delivery_note):
    """Entry point for a lightweight serviceability pre-check on a Delivery
    Note's shipping address -- distinct from the full Address Validation
    (street-level) and Service Availability (lane-level) checks."""
    dn = frappe.get_doc("Delivery Note", delivery_note)
    address_name = dn.shipping_address_name or dn.customer_address
    if not address_name:
        frappe.throw(f"{dn.name} has no shipping address to validate.")

    addr = frappe.get_doc("Address", address_name)
    country_code = frappe.db.get_value("Country", addr.country, "code") or ""
    return validate_postal_code(country_code, addr.pincode, state=addr.state)
