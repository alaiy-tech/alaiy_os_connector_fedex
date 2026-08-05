# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Whitelisted entry points the Alaiy OS connector card and the settings form
call to kick off / inspect syncs. These stay thin: create the log so it shows
up as "queued" immediately, then enqueue the real work on the long queue.
"""

import frappe

from alaiy_os_connector_fedex.fedex.sync import get_or_create_log


@frappe.whitelist()
def refresh_delivery_note_tracking(delivery_note):
    """Refresh one Delivery Note's FedEx status immediately (synchronous --
    a single tracking number is one fast API call, no need to queue it)."""
    from frappe.utils import now_datetime
    from alaiy_os_connector_fedex.fedex.tracking import track_shipments, _extract_status

    dn = frappe.get_doc("Delivery Note", delivery_note)
    if not dn.fedex_tracking_number:
        return {"success": False, "message": "No FedEx Tracking Number set on this Delivery Note."}

    results = track_shipments([dn.fedex_tracking_number])
    track_result = results.get(dn.fedex_tracking_number)
    if not track_result:
        return {"success": False, "message": "FedEx returned no tracking result for this number."}

    status = _extract_status(track_result) or "UNKNOWN"
    frappe.db.set_value("Delivery Note", dn.name, {
        "fedex_delivery_status": status[:140],
        "fedex_last_tracked_at": now_datetime(),
    })
    return {"success": True, "status": status}


@frappe.whitelist()
def trigger_pull_sync():
    """Manually enqueue a 'pull' sync (poll FedEx tracking for every tracked Delivery Note)."""
    log = get_or_create_log("pull", "manual")
    frappe.enqueue(
        "alaiy_os_connector_fedex.fedex.sync.run_pull_sync",
        queue="long",
        timeout=600,
        trigger="manual",
        log_name=log.name,
    )
    return {"queued": True, "log_name": log.name}


@frappe.whitelist()
def trigger_push_sync():
    """Manually enqueue a 'push' sync (Alaiy OS → external)."""
    log = get_or_create_log("push", "manual")
    frappe.enqueue(
        "alaiy_os_connector_fedex.fedex.sync.run_push_sync",
        queue="long",
        timeout=600,
        trigger="manual",
        log_name=log.name,
    )
    return {"queued": True, "log_name": log.name}


@frappe.whitelist()
def get_sync_status(sync_type=None):
    """
    Return the most recent FedEx Sync Log rows, newest first.

    The Alaiy OS connector card passes the registry slot name ("categories"
    or "items"); map those to this connector's own sync_type values.
    """
    filters = {}
    if sync_type:
        type_map = {"categories": "pull", "items": "push"}
        filters["sync_type"] = type_map.get(sync_type, sync_type)
    return frappe.get_all(
        "FedEx Sync Log",
        filters=filters,
        fields=[
            "name", "sync_type", "trigger", "status",
            "started_at", "finished_at",
            "items_processed", "items_created", "items_updated", "items_failed",
            "pages_total", "pages_done",
            "error_message",
        ],
        order_by="started_at desc",
        limit=5,
    )
