# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Shipment creation and cancellation via FedEx Ship API v1
(POST /ship/v1/shipments, PUT /ship/v1/shipments/cancel).

Schema reference: fedex/openapi/fedex-ship-api-openapi.yml. Same
permissive-schema caveat as rating.py -- no downloadable spec published
for this API.
"""

import base64

import frappe
from frappe.utils.file_manager import save_file

from alaiy_os_connector_fedex.fedex.client import FedexClient, FedexAPIError
from alaiy_os_connector_fedex.fedex.rating import _erpnext_address_to_fedex, _weight_uom_to_fedex

SHIPMENTS_PATH = "/ship/v1/shipments"
CANCEL_PATH = "/ship/v1/shipments/cancel"

# Default label format: PDF on standard half-page stock, usable without a
# thermal printer. Override via Settings for sites that have one.
_DEFAULT_LABEL_IMAGE_TYPE = "PDF"
_DEFAULT_LABEL_STOCK_TYPE = "PAPER_85X11_TOP_HALF_LABEL"


def _account_number():
    settings = frappe.get_single("FedEx Connector Settings")
    account_number = (settings.fedex_account_number or "").strip()
    if not account_number:
        raise RuntimeError("FedEx connector is not configured (Account Number missing).")
    return account_number, settings


def create_shipment(
    shipper, recipient, service_type, weight_value, weight_units="LB",
    packaging_type="YOUR_PACKAGING", dimensions=None, reference=None,
):
    """Creates a shipment and returns its label.

    shipper / recipient: dict with contact_name, phone, company_name,
    address_line, city, state, postal_code, country_code.
    Returns {tracking_number, label_bytes, label_content_type}.
    Raises FedexAPIError on any FedEx-side failure.
    """
    account_number, _settings = _account_number()

    dims = dimensions or {}
    package_item = {"weight": {"value": weight_value, "units": weight_units}}
    if dims.get("length") and dims.get("width") and dims.get("height"):
        package_item["dimensions"] = {
            "length": dims["length"], "width": dims["width"], "height": dims["height"],
            "units": dims.get("units", "IN"),
        }
    if reference:
        package_item["customerReferences"] = [
            {"customerReferenceType": "CUSTOMER_REFERENCE", "value": str(reference)[:40]}
        ]

    body = {
        "accountNumber": {"value": account_number},
        "labelResponseOptions": "LABEL",
        "requestedShipment": {
            "shipper": _contact_address_payload(shipper),
            "recipients": [_contact_address_payload(recipient)],
            "pickupType": "DROPOFF_AT_FEDEX_LOCATION",
            "serviceType": service_type,
            "packagingType": packaging_type,
            "shippingChargesPayment": {"paymentType": "SENDER"},
            "labelSpecification": {
                "imageType": _DEFAULT_LABEL_IMAGE_TYPE,
                "labelStockType": _DEFAULT_LABEL_STOCK_TYPE,
            },
            "requestedPackageLineItems": [package_item],
        },
    }

    client = FedexClient()
    resp = client.post(SHIPMENTS_PATH, json=body)
    return _parse_shipment_response(resp)


def _contact_address_payload(party):
    return {
        "contact": {
            "personName": party.get("contact_name") or "",
            "phoneNumber": party.get("phone") or "",
            "companyName": party.get("company_name") or "",
        },
        "address": {
            "streetLines": [party["address_line"]] if party.get("address_line") else [],
            "city": party.get("city") or "",
            "stateOrProvinceCode": party.get("state") or "",
            "postalCode": party.get("postal_code") or "",
            "countryCode": party.get("country_code") or "",
        },
    }


def _parse_shipment_response(resp):
    shipments = (resp.get("output") or {}).get("transactionShipments") or []
    if not shipments:
        raise FedexAPIError(
            "FedEx accepted the shipment request but returned no transactionShipments -- "
            f"raw response: {resp}",
        )
    shipment = shipments[0]
    tracking_number = shipment.get("masterTrackingNumber")
    if not tracking_number:
        raise FedexAPIError(f"FedEx shipment response had no masterTrackingNumber: {shipment}")

    label_bytes = None
    pieces = shipment.get("pieceResponses") or []
    if pieces:
        docs = pieces[0].get("packageDocuments") or []
        if docs and docs[0].get("encodedLabel"):
            label_bytes = base64.b64decode(docs[0]["encodedLabel"])

    return {
        "tracking_number": tracking_number,
        "label_bytes": label_bytes,
        "label_content_type": _DEFAULT_LABEL_IMAGE_TYPE,
    }


def cancel_shipment(tracking_number):
    account_number, _settings = _account_number()
    client = FedexClient()
    client.post(CANCEL_PATH, json={
        "accountNumber": {"value": account_number},
        "trackingNumber": tracking_number,
    })


@frappe.whitelist()
def create_shipment_for_delivery_note(delivery_note, service_type):
    """Entry point for a "Create FedEx Shipment" button on a Delivery
    Note. Resolves shipper/recipient/weight from ERPNext data, creates
    the shipment, and writes the tracking number and label back onto
    the DN."""
    dn = frappe.get_doc("Delivery Note", delivery_note)
    if dn.fedex_tracking_number:
        frappe.throw(
            f"{dn.name} already has a FedEx tracking number ({dn.fedex_tracking_number}) -- "
            "cancel the existing shipment first if you need to re-create it."
        )

    settings = frappe.get_single("FedEx Connector Settings")
    shipper_addr_name = settings.fedex_default_warehouse
    if not shipper_addr_name:
        frappe.throw("Set a Default Warehouse on FedEx Connector Settings before creating a shipment.")
    shipper = _erpnext_address_to_fedex(shipper_addr_name)
    shipper["company_name"] = settings.fedex_company or ""

    recipient_addr_name = dn.shipping_address_name or dn.customer_address
    if not recipient_addr_name:
        frappe.throw(f"{dn.name} has no shipping address to ship to.")
    recipient = _erpnext_address_to_fedex(recipient_addr_name)
    recipient["contact_name"] = dn.contact_person or dn.customer_name or ""
    recipient["company_name"] = dn.customer_name or ""

    weight = dn.total_net_weight or 0
    if not weight:
        frappe.throw(f"{dn.name} has no total net weight set -- required to create a shipment.")
    weight_units = _weight_uom_to_fedex(dn.weight_uom)

    try:
        result = create_shipment(
            shipper, recipient, service_type, weight_value=weight, weight_units=weight_units,
            reference=dn.name,
        )
    except FedexAPIError as e:
        frappe.throw(f"FedEx shipment creation failed: {e}")

    frappe.db.set_value("Delivery Note", dn.name, {
        "fedex_tracking_number": result["tracking_number"],
    })

    if result["label_bytes"]:
        file_doc = save_file(
            f"{dn.name}-fedex-label.pdf", result["label_bytes"],
            "Delivery Note", dn.name, is_private=1,
        )
        frappe.db.set_value("Delivery Note", dn.name, "fedex_label", file_doc.file_url)

    frappe.db.commit()
    return {"tracking_number": result["tracking_number"]}
