# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Track pull: poll FedEx shipment status for Delivery Notes carrying a
fedex_tracking_number, write the latest status back onto the DN.

Confirmed against fedex/openapi/fedex-track-api-openapi.yml (raw YAML read
directly, not paraphrased):

  POST /track/v1/trackingnumbers
  body: {"trackingInfo": [{"trackingNumberInfo": {"trackingNumber": "..."}}],
         "includeDetailedScans": false}
  -> {"output": {"completeTrackResults": [
        {"trackingNumber": "...", "trackResults": [{...}]}
     ]}}

Max 30 tracking numbers per request (spec's own maxItems on trackingInfo).

Documented, not guessed: the spec itself says trackResults' schema is
"intentionally permissive... consult the FedEx Developer Portal for full
payload field definitions" (additionalProperties: true, no fixed shape).
So the actual per-shipment status/scan fields below (latestStatusDetail,
scanEvents) are read defensively with .get() chains, same posture as
Flipkart's listings.py where a documented schema gap meant handling
multiple possible shapes rather than assuming one.

No inbound webhook here (unlike Flipkart) -- Track API's own
/track/v1/notifications is an OUTBOUND subscribe call (asks FedEx to send
email notifications), not a webhook receiver. Polling is the only pull
mechanism this connector implements.
"""

import json

import frappe
from frappe.utils import now_datetime

from alaiy_os_connector_fedex.fedex.client import FedexClient
from alaiy_os_connector_fedex.fedex.sync import get_or_create_log, _mark_running, _mark_finished

TRACK_PATH = "/track/v1/trackingnumbers"
_BATCH_SIZE = 30  # FedEx's own documented max per request


def _chunk(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _extract_status(track_result):
    """
    track_result is one entry of completeTrackResults[].trackResults[] --
    permissive/undocumented shape per the spec. Reads the commonly-present
    latestStatusDetail.description defensively; falls back to the raw
    statusByLocale-style shape a couple of real FedEx responses are known
    to use if description is missing.
    """
    latest = track_result.get("latestStatusDetail") or {}
    return (
        latest.get("description")
        or latest.get("statusByLocale")
        or latest.get("code")
        or None
    )


def track_shipments(tracking_numbers):
    """Direct call, no log -- used for a single Delivery Note's manual
    'Refresh Tracking' action. tracking_numbers: list of strings."""
    client = FedexClient()
    results = {}
    for batch in _chunk(tracking_numbers, _BATCH_SIZE):
        body = {
            "includeDetailedScans": False,
            "trackingInfo": [
                {"trackingNumberInfo": {"trackingNumber": tn}} for tn in batch
            ],
        }
        resp = client.post(TRACK_PATH, json=body)
        for entry in (resp.get("output") or {}).get("completeTrackResults") or []:
            tn = entry.get("trackingNumber")
            track_results = entry.get("trackResults") or []
            results[tn] = track_results[0] if track_results else None
    return results


def track_pending_deliveries(trigger="scheduled", log_name=None):
    """
    Full poll: every submitted Delivery Note with a fedex_tracking_number
    that isn't already marked DELIVERED gets its status refreshed.
    """
    log = get_or_create_log("track_pull", trigger, log_name)
    _mark_running(log)

    processed = updated = failed = 0
    try:
        dns = frappe.get_all(
            "Delivery Note",
            filters={
                "fedex_tracking_number": ["is", "set"],
                "fedex_delivery_status": ["!=", "DELIVERED"],
                "docstatus": 1,
            },
            fields=["name", "fedex_tracking_number"],
        )

        by_tracking_number = {dn.fedex_tracking_number: dn.name for dn in dns if dn.fedex_tracking_number}
        tracking_numbers = list(by_tracking_number.keys())

        for batch in _chunk(tracking_numbers, _BATCH_SIZE):
            try:
                results = track_shipments(batch)
            except Exception:
                failed += len(batch)
                processed += len(batch)
                frappe.log_error(
                    title="FedEx tracking batch failed",
                    message=frappe.get_traceback(),
                )
                continue

            for tn in batch:
                processed += 1
                dn_name = by_tracking_number.get(tn)
                track_result = results.get(tn)
                if not dn_name or not track_result:
                    failed += 1
                    continue
                try:
                    status = _extract_status(track_result)
                    frappe.db.set_value("Delivery Note", dn_name, {
                        "fedex_delivery_status": (status or "UNKNOWN")[:140],
                        "fedex_last_tracked_at": now_datetime(),
                    })
                    updated += 1
                except Exception:
                    failed += 1
                    frappe.log_error(
                        title=f"FedEx tracking update failed: {dn_name}",
                        message=json.dumps(track_result, default=str),
                    )

            log.items_processed = processed
            log.items_updated = updated
            log.items_failed = failed
            log.save(ignore_permissions=True)
            frappe.db.commit()

        _mark_finished(log, "success" if failed == 0 else "failed",
                        error_message=(f"{failed} shipment(s) failed to track -- see Error Log." if failed else None))
    except Exception:
        _mark_finished(log, "failed", frappe.get_traceback())
        frappe.log_error(title="FedEx track pull failed", message=frappe.get_traceback())
        raise

    return {"processed": processed, "updated": updated, "failed": failed}
