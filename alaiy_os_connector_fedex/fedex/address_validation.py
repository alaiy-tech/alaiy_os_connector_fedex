# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Address validation via FedEx Address Validation API v1
(POST /address/v1/addresses/resolve).

Schema reference: fedex/openapi/fedex-address-validation-api-openapi.yml.
Same permissive-schema caveat as rating.py/shipping.py.
"""

import frappe

from alaiy_os_connector_fedex.fedex.client import FedexClient

RESOLVE_PATH = "/address/v1/addresses/resolve"

# customerMessages codes documented as indicating an undeliverable or
# ambiguous match, rather than a cosmetic formatting difference.
_UNDELIVERABLE_MESSAGE_CODES = {"UNDELIVERABLE", "MULTIPLE_MATCHES_FOUND", "INVALID"}


def validate_address(address_line, city, state, postal_code, country_code):
    """Returns {classification, resolved, is_deliverable, messages}.
    resolved is the standardized address dict FedEx returned, or the
    input echoed back if nothing came back. Raises FedexAPIError via
    FedexClient on a request-level failure; a per-address validation
    problem (ambiguous, undeliverable) is returned in messages, not
    raised, since that's a real business outcome, not an API error."""
    client = FedexClient()
    body = {
        "addressesToValidate": [{
            "address": {
                "streetLines": [address_line] if address_line else [],
                "city": city or "",
                "stateOrProvinceCode": state or "",
                "postalCode": postal_code or "",
                "countryCode": country_code or "",
            }
        }]
    }
    resp = client.post(RESOLVE_PATH, json=body)
    resolved_addresses = (resp.get("output") or {}).get("resolvedAddresses") or []
    if not resolved_addresses:
        return {
            "classification": "UNKNOWN", "resolved": None,
            "is_deliverable": False, "messages": ["No resolvedAddresses in response."],
        }

    result = resolved_addresses[0]
    messages = [m.get("message", "") for m in (result.get("customerMessages") or [])]
    message_codes = {m.get("code") for m in (result.get("customerMessages") or [])}
    is_deliverable = not (message_codes & _UNDELIVERABLE_MESSAGE_CODES)

    return {
        "classification": result.get("classification", "UNKNOWN"),
        "resolved": result,
        "is_deliverable": is_deliverable,
        "messages": messages,
    }


@frappe.whitelist()
def validate_delivery_note_address(delivery_note):
    """Entry point for a "Validate Address" button on a Delivery Note.
    Validates the DN's shipping address before shipment creation."""
    dn = frappe.get_doc("Delivery Note", delivery_note)
    address_name = dn.shipping_address_name or dn.customer_address
    if not address_name:
        frappe.throw(f"{dn.name} has no shipping address to validate.")

    addr = frappe.get_doc("Address", address_name)
    country_code = frappe.db.get_value("Country", addr.country, "code") or ""
    return validate_address(addr.address_line1, addr.city, addr.state, addr.pincode, country_code)
