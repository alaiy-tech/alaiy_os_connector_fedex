# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Rate quotes via FedEx Rate API v1 (POST /rate/v1/rates/quotes).

Schema reference: fedex/openapi/fedex-rate-api-openapi.yml. FedEx has not
published a downloadable spec for this API; the schema is derived from
the stable v1 request/response shape and treated as permissive on parse.
"""

import frappe

from alaiy_os_connector_fedex.fedex.client import FedexClient, FedexAPIError

RATE_QUOTES_PATH = "/rate/v1/rates/quotes"


def _address_payload(address_line, city, state, postal_code, country_code):
    return {
        "address": {
            "streetLines": [address_line] if address_line else [],
            "city": city or "",
            "stateOrProvinceCode": state or "",
            "postalCode": postal_code or "",
            "countryCode": country_code or "",
        }
    }


def _package_line_items(weight_value, weight_units, length=None, width=None, height=None, dim_units="IN"):
    item = {"weight": {"value": weight_value, "units": weight_units}}
    if length and width and height:
        item["dimensions"] = {
            "length": length, "width": width, "height": height, "units": dim_units,
        }
    return [item]


def get_rate_quotes(
    shipper_address, recipient_address, weight_value, weight_units="LB",
    service_type=None, dimensions=None, rate_request_type=None,
):
    """Returns available FedEx service quotes for a single package.

    shipper_address / recipient_address: dict with address_line, city,
    state, postal_code, country_code.
    dimensions: optional dict with length/width/height/units.
    service_type: omit to request every eligible service; pass a FedEx
    service code (e.g. "FEDEX_GROUND") to restrict to one.

    Returns a list of {service_type, transit_days, total_net_charge,
    currency} in FedEx's own response order. Raises FedexAPIError on any
    FedEx-side failure (invalid address, missing account number, etc.).
    """
    client = FedexClient()
    settings = frappe.get_single("FedEx Connector Settings")
    account_number = (settings.fedex_account_number or "").strip()
    if not account_number:
        raise RuntimeError("FedEx connector is not configured (Account Number missing).")

    dims = dimensions or {}
    body = {
        "accountNumber": {"value": account_number},
        "requestedShipment": {
            "shipper": _address_payload(**shipper_address),
            "recipient": _address_payload(**recipient_address),
            "pickupType": "DROPOFF_AT_FEDEX_LOCATION",
            "rateRequestType": rate_request_type or ["LIST", "ACCOUNT"],
            "requestedPackageLineItems": _package_line_items(
                weight_value, weight_units,
                dims.get("length"), dims.get("width"), dims.get("height"), dims.get("units", "IN"),
            ),
        },
    }
    if service_type:
        body["requestedShipment"]["serviceType"] = service_type

    resp = client.post(RATE_QUOTES_PATH, json=body)
    return _parse_rate_reply(resp)


def _parse_rate_reply(resp):
    """Skips any rateReplyDetails entry with no ratedShipmentDetails
    (a partial reply is valid, not an error)."""
    results = []
    for detail in (resp.get("output") or {}).get("rateReplyDetails") or []:
        rated = detail.get("ratedShipmentDetails") or []
        if not rated:
            continue
        # Live sandbox response confirmed totalNetCharge is a plain number,
        # not the nested {amount, currency} dict the derived spec assumed.
        # Handle both shapes.
        charge = rated[0].get("totalNetCharge")
        if isinstance(charge, dict):
            amount, currency = charge.get("amount"), charge.get("currency")
        else:
            amount, currency = charge, rated[0].get("currency")
        commit = detail.get("commit") or {}
        results.append({
            "service_type": detail.get("serviceType"),
            "transit_days": commit.get("transitDays") or commit.get("commitMessageDetails"),
            "total_net_charge": amount,
            "currency": currency,
        })
    return results


@frappe.whitelist()
def get_rate_quotes_for_delivery_note(delivery_note):
    """Entry point for a "Get FedEx Rates" button on a Delivery Note.
    Resolves shipper (Default Warehouse address), recipient (DN shipping
    address), and weight (DN total_net_weight) from ERPNext data."""
    dn = frappe.get_doc("Delivery Note", delivery_note)
    settings = frappe.get_single("FedEx Connector Settings")

    shipper_addr_name = settings.fedex_default_warehouse
    if not shipper_addr_name:
        frappe.throw("Set a Default Warehouse on FedEx Connector Settings before getting rates.")
    shipper = _erpnext_address_to_fedex(shipper_addr_name)

    recipient_addr_name = dn.shipping_address_name or dn.customer_address
    if not recipient_addr_name:
        frappe.throw(f"{dn.name} has no shipping address to rate against.")
    recipient = _erpnext_address_to_fedex(recipient_addr_name)

    weight = dn.total_net_weight or 0
    if not weight:
        frappe.throw(f"{dn.name} has no total net weight set -- required for a real rate quote.")
    weight_units = _weight_uom_to_fedex(dn.weight_uom)

    try:
        return get_rate_quotes(shipper, recipient, weight_value=weight, weight_units=weight_units)
    except FedexAPIError as e:
        frappe.throw(f"FedEx rate request failed: {e}")


def _weight_uom_to_fedex(weight_uom):
    """Maps an ERPNext Weight UOM to FedEx's LB/KG enum. Raises on any
    other unit instead of silently mis-rating the shipment."""
    normalized = (weight_uom or "").strip().lower()
    if normalized in ("kg", "kilogram", "kilograms"):
        return "KG"
    if normalized in ("lb", "lbs", "pound", "pounds", ""):
        return "LB"
    frappe.throw(
        f"Weight UOM {weight_uom!r} has no FedEx equivalent (only LB/KG are supported) -- "
        "convert the Delivery Note's weight to kg or lb first."
    )


def _erpnext_address_to_fedex(address_name):
    addr = frappe.get_doc("Address", address_name)
    return {
        "address_line": addr.address_line1,
        "city": addr.city,
        "state": addr.state,
        "postal_code": addr.pincode,
        "country_code": frappe.db.get_value("Country", addr.country, "code") or "",
    }
