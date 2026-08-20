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

    warehouse_name = _resolve_shipper_warehouse(dn, settings)
    shipper = _warehouse_to_fedex(warehouse_name, dn.company)
    shipper["company_name"] = settings.fedex_company or ""

    recipient_addr_name = dn.shipping_address_name or dn.customer_address
    if not recipient_addr_name:
        frappe.throw(f"{dn.name} has no shipping address to rate against.")
    recipient = _erpnext_address_to_fedex(recipient_addr_name)

    weight = dn.total_net_weight or 0
    if not weight:
        frappe.throw(f"{dn.name} has no total net weight set -- required for a real rate quote.")
    # weight_uom lives per line item on Delivery Note, not on the DN header
    # itself (same real gap as shipping.py's create_shipment_for_delivery_note).
    item_weight_uom = next((row.weight_uom for row in dn.items if row.weight_uom), None)
    weight_units = _weight_uom_to_fedex(item_weight_uom)

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


# ERPNext's Address.state is free text -- Frappe's own address forms let
# users type the full state name ("Georgia") instead of the 2-letter code
# FedEx requires ("GA"). Confirmed live: FedEx rejected a real shipment
# with RECIPIENTS.ADDRESSSTATEORPROVINCECODE.MISMATCH for exactly this
# reason, for a perfectly valid Georgia zip code. pycountry (already a
# frappe core dependency -- see frappe/geo/doctype/country/country.py)
# has the real ISO 3166-2 subdivision data, no need to hand-maintain one.
def _normalize_state(state, country_code):
    if not state or len(state) == 2:
        return state or ""
    import pycountry

    try:
        match = pycountry.subdivisions.lookup(f"{country_code}-{state}")
    except LookupError:
        match = next(
            (s for s in pycountry.subdivisions.get(country_code=country_code) or []
             if s.name.lower() == state.strip().lower()),
            None,
        )
    return match.code.split("-")[-1] if match else state


def _erpnext_address_to_fedex(address_name):
    addr = frappe.get_doc("Address", address_name)
    country_code = frappe.db.get_value("Country", addr.country, "code") or ""
    country_code = country_code.upper()
    return {
        "phone": addr.phone or "",
        "address_line": addr.address_line1,
        "city": addr.city,
        "state": _normalize_state(addr.state, country_code),
        "postal_code": addr.pincode,
        "country_code": country_code,
    }


def _resolve_shipper_warehouse(dn, settings):
    """
    Generic across both a single-warehouse site (altomoda) and a
    many-suppliers-many-warehouses site (thesolist, dropship model) --
    each supplier already gets their own Warehouse there, named after the
    supplier (see alaiy_os_thesolist's own _get_supplier_warehouse
    convention), so the DN's own item warehouse IS the real per-order
    shipper once one exists.

    Prefers the DN's own item warehouse(s) -- if every item ships from the
    same one, that's unambiguously the real shipper for THIS order, more
    correct than a single site-wide default. Falls back to
    Settings.fedex_default_warehouse only when the DN's items don't
    disambiguate (blank warehouse, e.g. an older/manually-built DN).
    Throws rather than guessing if a DN's items genuinely span more than
    one warehouse -- same posture as Unicommerce's own
    _get_facility_code, which throws on "Multiple facility codes found in
    a single order" instead of picking one arbitrarily.
    """
    warehouses = {row.warehouse for row in dn.items if row.warehouse}
    if len(warehouses) > 1:
        frappe.throw(
            f"{dn.name} has items from multiple warehouses ({', '.join(sorted(warehouses))}) -- "
            "FedEx needs one shipper per shipment. Split this into separate Delivery Notes per warehouse."
        )
    if warehouses:
        return next(iter(warehouses))

    if not settings.fedex_default_warehouse:
        frappe.throw(
            f"{dn.name}'s items have no warehouse set, and no Default Warehouse is "
            "configured on FedEx Connector Settings -- nothing to resolve the shipper from."
        )
    return settings.fedex_default_warehouse


def _warehouse_to_fedex(warehouse_name, company):
    """
    FedEx Connector Settings.fedex_default_warehouse is a Link to Warehouse,
    not Address -- confirmed live: passing it into _erpnext_address_to_fedex
    raised "Address <warehouse name> not found" outright. Warehouse carries
    its own flat address fields (address_line_1/2, city, state, pin,
    phone_no) rather than a linked Address, and has no country field of its
    own.

    Country resolution: prefers Settings.fedex_shipper_country. Falls back
    to the Company's registered country only when that's unset -- confirmed
    live that blindly using the Company's country is wrong whenever the
    warehouse actually ships from elsewhere (FedEx rejected the request:
    "ORIGIN.COUNTRY.NOTSERVED" when a Company registered in one country was
    used as the ship-from for a warehouse address physically in another).
    """
    wh = frappe.get_doc("Warehouse", warehouse_name)
    if not (wh.address_line_1 and wh.city and wh.pin):
        frappe.throw(
            f"Warehouse {warehouse_name} has no address set (address_line_1/city/pin) -- "
            "fill in the Warehouse's address before using it as the FedEx shipper."
        )
    country = (
        frappe.db.get_single_value("FedEx Connector Settings", "fedex_shipper_country")
        or frappe.get_cached_value("Company", company, "country")
    )
    return {
        "contact_name": wh.warehouse_name,
        "phone": wh.phone_no or "",
        "address_line": wh.address_line_1,
        "city": wh.city,
        "state": wh.state or "",
        "postal_code": wh.pin,
        "country_code": frappe.db.get_value("Country", country, "code") or "" if country else "",
    }
