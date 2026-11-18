# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""The tracking schedule must look at the log rows the tracking job actually writes.

The tracking job logs its runs under sync type "track_pull". The scheduler used to look for "pull",
found nothing, and queued the job on every one-minute tick no matter what interval was set. These
tests use a stand-in for Frappe: no bench, no database.
"""

import importlib
import sys
import types
import unittest
from datetime import datetime, timedelta

NOW = datetime(2026, 11, 18, 12, 0, 0)


class SyncJobTests(unittest.TestCase):
    def setUp(self):
        self.enqueued, self.lookups = [], []
        self.rows = []  # log rows the stand-in database holds: dicts with sync_type, status, trigger, started_at
        outer = self

        frappe = types.ModuleType("frappe")
        frappe.db = types.SimpleNamespace(exists=lambda *a, **k: True, get_value=self.get_value)
        frappe.get_single = lambda doctype: types.SimpleNamespace(
            is_enabled=1, fedex_pull_sync_interval="5 min", fedex_push_sync_interval="Disabled")
        frappe.enqueue = lambda fn, **kw: outer.enqueued.append((fn, kw))
        utils = types.ModuleType("frappe.utils")
        utils.now_datetime = lambda: NOW
        utils.add_to_date = lambda value, minutes=0: value + timedelta(minutes=minutes)

        self.saved = {name: sys.modules.get(name) for name in ("frappe", "frappe.utils", "alaiy_os_connector_fedex.fedex.sync_jobs")}
        sys.modules.update({"frappe": frappe, "frappe.utils": utils})
        sys.modules.pop("alaiy_os_connector_fedex.fedex.sync_jobs", None)
        self.sync_jobs = importlib.import_module("alaiy_os_connector_fedex.fedex.sync_jobs")

    def tearDown(self):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def get_value(self, doctype, filters, fieldname, order_by=None):
        """The newest started_at among rows matching every filter, as the real query would return."""
        self.lookups.append(dict(filters))

        def matches(row):
            for key, wanted in filters.items():
                if isinstance(wanted, list) and wanted[0] == "!=":
                    if row.get(key) == wanted[1]:
                        return False
                elif row.get(key) != wanted:
                    return False
            return True

        found = sorted((r[fieldname] for r in self.rows if matches(r)), reverse=True)
        return found[0] if found else None

    def row(self, minutes_ago, sync_type="track_pull", status="success", trigger="scheduled"):
        self.rows.append({"sync_type": sync_type, "status": status, "trigger": trigger,
                          "started_at": NOW - timedelta(minutes=minutes_ago)})

    def test_a_recent_tracking_run_means_nothing_is_due(self):
        self.row(1)
        self.sync_jobs.check_and_enqueue()
        self.assertEqual(self.enqueued, [])

    def test_a_tracking_run_older_than_the_interval_is_due(self):
        self.row(6)
        self.sync_jobs.check_and_enqueue()
        self.assertEqual(len(self.enqueued), 1)
        self.assertEqual(self.enqueued[0][0], "alaiy_os_connector_fedex.fedex.sync.run_pull_sync")

    def test_a_tracking_run_still_in_progress_blocks_a_second_one(self):
        self.row(2, status="running")
        self.sync_jobs.check_and_enqueue()
        self.assertEqual(self.enqueued, [])

    def test_the_lookups_use_the_type_the_tracking_job_writes(self):
        self.sync_jobs.check_and_enqueue()
        self.assertTrue(self.lookups)
        self.assertEqual({f["sync_type"] for f in self.lookups}, {"track_pull"})

    def test_a_notification_row_that_reads_running_does_not_block_the_poll(self):
        self.row(2, status="running", trigger="webhook")
        self.sync_jobs.check_and_enqueue()
        self.assertEqual(len(self.enqueued), 1)

    def test_a_notification_row_is_not_a_tracking_run(self):
        # Webhook notifications are logged under the same sync type; one must not hold back the poll.
        self.row(1, trigger="webhook")
        self.sync_jobs.check_and_enqueue()
        self.assertEqual(len(self.enqueued), 1)


class ManualTriggerTests(unittest.TestCase):
    def setUp(self):
        self.created, self.enqueued = [], []
        frappe = types.ModuleType("frappe")
        frappe.whitelist = lambda *a, **k: (lambda fn: fn)
        frappe.enqueue = lambda fn, **kw: self.enqueued.append((fn, kw))
        frappe.get_all = lambda doctype, **kw: self.created.append(("get_all", kw)) or []
        utils = types.ModuleType("frappe.utils")
        utils.now_datetime = lambda: NOW
        names = ("frappe", "frappe.utils", "alaiy_os_connector_fedex.api.sync", "alaiy_os_connector_fedex.fedex.sync")
        self.saved = {name: sys.modules.get(name) for name in names}
        sys.modules.update({"frappe": frappe, "frappe.utils": utils})
        for name in names[2:]:
            sys.modules.pop(name, None)
        sync = importlib.import_module("alaiy_os_connector_fedex.api.sync")
        self.api = sync
        sync.get_or_create_log = lambda sync_type, trigger, log_name=None: (
            self.created.append((sync_type, trigger)) or types.SimpleNamespace(name="LOG-1"))

    def tearDown(self):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_a_manual_tracking_run_is_logged_under_the_tracking_type(self):
        self.api.trigger_pull_sync()
        self.assertEqual(self.created, [("track_pull", "manual")])

    def test_the_status_view_for_the_pull_slot_reads_the_tracking_type(self):
        self.api.get_sync_status("categories")
        self.assertEqual(self.created[-1][1]["filters"], {"sync_type": "track_pull"})


if __name__ == "__main__":
    unittest.main()
