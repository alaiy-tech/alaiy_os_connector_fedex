"""
Single source of truth for this connector's registration metadata.
Consumed by setup/install.py → upserted into alaiy_os's OS Connector Registry.
"""

connector_meta = {
    "connector_id": "fedex",
    "connector_name": "FedEx",
    "connector_app": "alaiy_os_connector_fedex",
    # Neither "channel" (sell TO) nor "supplier" (buy FROM) fits a carrier --
    # FedEx moves shipments for orders that already exist, it doesn't sell
    # or supply anything. Using "channel" as the closest existing bucket
    # until/unless the registry adds a real "carrier" type.
    "connector_type": "channel",
    "description": "FedEx connector — shipment tracking, rating, and label generation via the FedEx Ship/Track/Rate APIs.",
    "icon": "box",
    "icon_url": "",
    "settings_doctype": "FedEx Connector Settings",
    "test_method": "alaiy_os_connector_fedex.api.test_connection.test_connection",
    # The registry exposes two sync "slots". Map them to whatever your
    # connector actually does; the labels are what the UI shows.
    "sync_categories_method": "alaiy_os_connector_fedex.api.sync.trigger_pull_sync",
    "sync_items_method": "alaiy_os_connector_fedex.api.sync.trigger_push_sync",
    "sync_status_method": "alaiy_os_connector_fedex.api.sync.get_sync_status",
    "sync_categories_label": "Pull",
    "sync_items_label": "Push",
    "is_enabled": 0,
    "connection_status": "untested",
}
