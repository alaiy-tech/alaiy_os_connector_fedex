# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Inbound tracking-event notifications from FedEx's Shipment Visibility
Webhook (svm/v1). Structure only -- request signing/verification is not
implemented, because FedEx's subscription and payload signing scheme is
not documented anywhere in this repo's cached docs, and the docs.fedex.com
page for it is JS-rendered with no downloadable spec without portal
login (same gap as Ship/Rate before their specs were added).

receive_notification is intentionally guarded off (returns 501) until
that spec is available -- exposing an unauthenticated write endpoint
that accepts arbitrary tracking-status updates onto Delivery Notes is a
real security hole, not a stub worth leaving open "for now".

To complete: export the Shipment Visibility Webhook's OpenAPI spec (or
at minimum its subscription request/response and signing-header
convention) from the FedEx dev portal into fedex/openapi/, then:
  1. implement verify_signature() against the real scheme
  2. remove the 501 guard in receive_notification
  3. add a subscribe_webhook() call using the account's real subscription
     endpoint once its request shape is known
"""

import json

import frappe

from alaiy_os_connector_fedex.fedex.tracking import _extract_status


def _log_event(event_type, trigger_status, payload):
    frappe.get_doc({
        "doctype": "FedEx Sync Log",
        "sync_type": "track_pull",
        "trigger": "webhook",
        "status": trigger_status,
        "log_messages": f"{event_type}: {json.dumps(payload, default=str)[:9000]}",
    }).insert(ignore_permissions=True)
    frappe.db.commit()


def verify_signature(request):
    """Not implemented -- see module docstring. Always returns False so
    receive_notification cannot be made live by accident before this is
    filled in against the real FedEx signing scheme."""
    return False


def _handle_tracking_event(payload):
    """Permissive parse, same posture as tracking.py's poll path --
    FedEx's own docs describe the poll response as intentionally
    permissive; the webhook payload is assumed to carry an equivalent
    trackingNumberInfo/latestStatusDetail shape until the real spec
    confirms otherwise."""
    tracking_number = (
        (payload.get("trackingNumberInfo") or {}).get("trackingNumber")
        or payload.get("trackingNumber")
    )
    if not tracking_number:
        _log_event(payload.get("eventType", "tracking_update"), "failed", payload)
        return

    dn_name = frappe.db.get_value(
        "Delivery Note", {"fedex_tracking_number": tracking_number, "docstatus": ["!=", 2]}, "name"
    )
    if not dn_name:
        _log_event(payload.get("eventType", "tracking_update"), "skipped", payload)
        return

    status = _extract_status(payload)
    frappe.db.set_value("Delivery Note", dn_name, {
        "fedex_delivery_status": (status or "UNKNOWN")[:140],
        "fedex_last_tracked_at": frappe.utils.now_datetime(),
    })
    frappe.db.commit()
    _log_event(payload.get("eventType", "tracking_update"), "success", payload)


@frappe.whitelist(allow_guest=True)
def receive_notification():
    """Entry point for FedEx's Shipment Visibility Webhook. Disabled
    (501) until verify_signature is implemented against the real FedEx
    signing scheme -- see module docstring."""
    frappe.local.response.http_status_code = 501
    return {"error": "FedEx webhook receiver not yet implemented -- signing scheme undocumented."}
