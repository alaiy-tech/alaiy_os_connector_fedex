# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Postal code validation via FedEx Postal Code Validation API v1
(POST /country/v1/postal/validate -- "Validate Postal" operation).

Confirmed against the real FedEx Developer Portal v1 REST API docs
(developer.fedex.com/api/en-us/catalog/postal-code/v1/docs.html), not
assumed from fedex.md's plain-English summary alone.
"""

import frappe

from alaiy_os_connector_fedex.fedex.client import FedexClient

VALIDATE_PATH = "/country/v1/postal/validate"


def validate_postal_code(country_code, postal_code, state=None, ship_date=None,
                          carrier_code="FDXG", check_for_mismatch=True):
    """Validates a postal/state/country combination independent of a full
    street address. Per fedex.md: postal alignment and territory alignment
    are separate outputs -- do not cross-reference them.

    state is required for US/CA/MX per the spec; non-postal-aware countries
    can pass a placeholder postal_code (FedEx documents "00000" for these).

    Returns {is_valid, cleaned_postal_code, location_descriptions, alerts, raw}.
    Raises FedexAPIError via FedexClient on a request-level failure.
    """
    client = FedexClient()
    body = {
        "carrierCode": carrier_code,
        "checkForMismatch": check_for_mismatch,
        "countryCode": country_code or "",
        "postalCode": postal_code or "",
    }
    if state:
        body["stateOrProvinceCode"] = state
    if ship_date:
        body["shipDate"] = ship_date

    resp = client.post(VALIDATE_PATH, json=body)
    output = resp.get("output") or {}

    # A mismatch alert (e.g. STATE.MISMATCH) is still a successful call with
    # real location data -- only the absence of a cleaned postal code means
    # the combination genuinely couldn't be resolved.
    return {
        "is_valid": bool(output.get("cleanedPostalCode")),
        "cleaned_postal_code": output.get("cleanedPostalCode"),
        "location_descriptions": output.get("locationDescriptions") or [],
        "alerts": output.get("alerts") or [],
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
