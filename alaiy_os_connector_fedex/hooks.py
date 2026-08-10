app_name = "alaiy_os_connector_fedex"
app_title = "Alaiy Os Connector Fedex"
app_publisher = "Alaiy"
app_description = "FedEx connector for AlaiyOS"
app_email = "mail@alaiy.com"
app_license = "agpl-3.0"

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
# Every Alaiy OS connector runs on top of alaiy_os (registry, workspace,
# connector card) and erpnext (Item, Sales Order, Warehouse, ...).
required_apps = ["alaiy_os", "erpnext"]

# ---------------------------------------------------------------------------
# Installation / migration
# ---------------------------------------------------------------------------
# after_install runs once on `bench install-app`; after_migrate runs on every
# `bench migrate`. sync_connector_registry() (re)registers this connector in
# alaiy_os's OS Connector Registry and is idempotent, so it is safe on migrate.
after_install = [
    "alaiy_os_connector_fedex.setup.install.after_install"
]

after_migrate = [
    "alaiy_os_connector_fedex.setup.install.sync_connector_registry"
]

# ---------------------------------------------------------------------------
# Alaiy OS sidebar
# ---------------------------------------------------------------------------
# Register this connector's Sync Log under the Alaiy OS "Logs" sidebar section.
# alaiy_os reads this hook in create_or_update_workspace_sidebar().
alaiy_os_sidebar_log_items = [
    {
        "link_type": "DocType",
        "link_to": "FedEx Sync Log",
        "label": "FedEx Logs",
        "icon": "activity",
    }
]

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
# Runs every minute; check_and_enqueue() decides whether any sync is actually
# due based on the intervals configured in FedEx Connector Settings.
scheduler_events = {
    "cron": {
        "* * * * *": [
            "alaiy_os_connector_fedex.fedex.sync_jobs.check_and_enqueue"
        ]
    }
}

# ---------------------------------------------------------------------------
# Document events (examples — wire up the ones your connector needs)
# ---------------------------------------------------------------------------
# doc_events = {
# 	"Item": {
# 		"after_insert": "alaiy_os_connector_fedex.fedex.sync.on_item_change",
# 		"on_update": "alaiy_os_connector_fedex.fedex.sync.on_item_change",
# 	},
# 	"Sales Order": {
# 		"on_submit": "alaiy_os_connector_fedex.fedex.sync.on_sales_order_submit",
# 	},
# }

# List-view client scripts for ERPNext doctypes (examples)
# doctype_list_js = {
# 	"Item": "public/js/item_list.js",
# }
