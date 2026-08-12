# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Service Availability API v1 -- three separate operations, three separate
endpoints (not one endpoint with three request shapes):

  Retrieve Services and Packaging Options -> POST /availability/v1/packageandserviceoption
  Retrieve Special Service Options        -> POST /availability/v1/specialserviceoptions
  Retrieve Services and Transit Times     -> POST /availability/v1/transittimes

Confirmed against the real FedEx REST SDK generated from FedEx's own OpenAPI
models (github.com/ShipStream/fedex-rest-php-sdk), not assumed from fedex.md's
plain-English summary alone -- the transittimes path was directly verified
against that SDK's actual request-building source, not just its docs.

Per fedex.md: one carrier code (FDXE/FDXG) per request for some operations --
callers pass carrier_codes explicitly rather than this module defaulting to
"query everything", since a mixed FDXE+FDXG request may not behave the same
as fedex.md's other single-carrier-per-request constraints (unconfirmed
either way -- pass what you actually need tested).
"""

import frappe

from alaiy_os_connector_fedex.fedex.client import FedexClient

PACKAGE_AND_SERVICE_OPTIONS_PATH = "/availability/v1/packageandserviceoption"
SPECIAL_SERVICE_OPTIONS_PATH = "/availability/v1/specialserviceoptions"
TRANSIT_TIMES_PATH = "/availability/v1/transittimes"


def _address_payload(postal_code, country_code, city=None, state=None):
    address = {"postalCode": postal_code or "", "countryCode": country_code or ""}
    if city:
        address["city"] = city
    if state:
        address["stateOrProvinceCode"] = state
    return {"address": address}


def get_transit_times(shipper_postal_code, shipper_country, recipient_postal_code, recipient_country,
                       weight_value, weight_units="LB", ship_date=None, carrier_codes=None):
    """Available services + delivery commit/transit-time info for a lane.
    Returns the raw output.transitTimes list -- each entry carries
    serviceType, serviceName, commit (the real delivery-window object), and
    per-entry customerMessages/alerts."""
    client = FedexClient()
    body = {
        "requestedShipment": {
            "shipper": _address_payload(shipper_postal_code, shipper_country),
            "recipient": _address_payload(recipient_postal_code, recipient_country),
            "requestedPackageLineItems": [{"weight": {"units": weight_units, "value": weight_value}}],
        },
        "carrierCodes": carrier_codes or ["FDXE", "FDXG"],
    }
    if ship_date:
        body["requestedShipment"]["shipDateStamp"] = ship_date

    resp = client.post(TRANSIT_TIMES_PATH, json=body)
    output = resp.get("output") or {}
    return {"transit_times": output.get("transitTimes") or [], "alerts": output.get("alerts") or []}


def get_package_and_service_options(shipper_postal_code, shipper_country, recipient_postal_code,
                                     recipient_country, weight_value, weight_units="LB",
                                     ship_date=None, account_number=None, carrier_codes=None):
    """Which FedEx services + packaging types are actually sellable for
    this lane -- the authoritative "can I ship this, with what" check."""
    client = FedexClient()
    body = {
        "requestedShipment": {
            "shipper": _address_payload(shipper_postal_code, shipper_country),
            "recipients": [_address_payload(recipient_postal_code, recipient_country)],
            "requestedPackageLineItems": [{"weight": {"units": weight_units, "value": weight_value}}],
        },
    }
    if ship_date:
        body["requestedShipment"]["shipDateStamp"] = ship_date
    if carrier_codes:
        body["carrierCodes"] = carrier_codes
    if account_number:
        body["accountNumber"] = {"value": account_number}

    resp = client.post(PACKAGE_AND_SERVICE_OPTIONS_PATH, json=body)
    output = resp.get("output") or {}
    return {
        "package_options": output.get("packageOptions") or [],
        "service_options": output.get("serviceOptions") or [],
        "one_rate": output.get("oneRate"),
        "alerts": output.get("alerts") or [],
    }


def get_special_service_options(shipper_postal_code, shipper_country, recipient_postal_code,
                                 recipient_country, weight_value, weight_units="LB",
                                 packaging_type="YOUR_PACKAGING", ship_date=None,
                                 account_number=None, carrier_codes=None):
    """Which special services (signature options, Saturday delivery,
    dangerous goods, return types, ...) are actually selectable for this
    specific shipment -- filtered by carrier/service, not a static list."""
    client = FedexClient()
    body = {
        "requestedShipment": {
            "shipper": _address_payload(shipper_postal_code, shipper_country),
            "recipient": _address_payload(recipient_postal_code, recipient_country),
            "packagingType": packaging_type,
            "requestedPackageLineItems": [{"weight": {"units": weight_units, "value": weight_value}}],
        },
    }
    if ship_date:
        body["requestedShipment"]["shipDateStamp"] = ship_date
    if carrier_codes:
        body["carrierCodes"] = carrier_codes
    if account_number:
        body["accountNumber"] = {"value": account_number}

    resp = client.post(SPECIAL_SERVICE_OPTIONS_PATH, json=body)
    output = resp.get("output") or {}
    return {"service_options_list": output.get("serviceOptionsList") or [], "alerts": output.get("alerts") or []}
