# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
The actual sync work + the FedEx Sync Log lifecycle helpers every sync
shares. run_pull_sync delegates to fedex/tracking.py (the only pull FedEx
has -- shipment status). run_push_sync is a stub: FedEx's "push" direction
(creating shipments/labels via the Ship API) isn't implemented yet.
"""

import frappe
from frappe.utils import now_datetime


def get_or_create_log(sync_type, trigger, log_name=None):
    """
    Return the Sync Log to use for this run. If log_name is given (the API
    layer pre-created it so it shows as 'queued' immediately) reuse it;
    otherwise create a fresh one. Newly created logs start as 'queued'.
    """
    if log_name and frappe.db.exists("FedEx Sync Log", log_name):
        return frappe.get_doc("FedEx Sync Log", log_name)

    log = frappe.new_doc("FedEx Sync Log")
    log.sync_type = sync_type
    log.trigger = trigger
    log.status = "queued"
    log.insert(ignore_permissions=True)
    frappe.db.commit()
    return log


def _mark_running(log):
    log.status = "running"
    log.started_at = now_datetime()
    log.save(ignore_permissions=True)
    frappe.db.commit()


def _mark_finished(log, status, error_message=None):
    log.status = status
    log.finished_at = now_datetime()
    if error_message:
        log.error_message = error_message[:2000]
    log.save(ignore_permissions=True)
    frappe.db.commit()


def _run(sync_type, trigger, log_name, worker):
    log = get_or_create_log(sync_type, trigger, log_name)
    _mark_running(log)
    try:
        worker(log)
        _mark_finished(log, "success")
    except Exception:
        _mark_finished(log, "failed", frappe.get_traceback())
        frappe.log_error(
            title=f"FedEx connector: {sync_type} sync failed",
            message=frappe.get_traceback(),
        )
        raise


def run_pull_sync(trigger="scheduled", log_name=None):
    """Poll FedEx shipment status for every tracked Delivery Note."""
    from alaiy_os_connector_fedex.fedex.tracking import track_pending_deliveries
    track_pending_deliveries(trigger=trigger, log_name=log_name)


def run_push_sync(trigger="scheduled", log_name=None):
    """
    Create shipments/labels via the FedEx Ship API. TODO: implement -- needs
    the same docs-verification pass tracking.py went through (Ship API
    request shape, package/dimension requirements, label format) before any
    real logic gets written here.
    """
    def worker(log):
        pass

    _run("push", trigger, log_name, worker)
