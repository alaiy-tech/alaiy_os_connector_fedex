# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Reachability check for the saved credentials. Wired into the registry via
connector_meta["test_method"] and called by the "Test Connection" button.
Always returns {"success": bool, "message": str} — never raises to the caller.

FedEx has no generic /ping endpoint (same situation as Flipkart) -- the only
reliable reachability check is actually performing the OAuth2 exchange.
"""

import frappe


@frappe.whitelist()
def test_connection():
    doc = frappe.get_single("FedEx Connector Settings")
    if not doc.fedex_client_id:
        return {"success": False, "message": "Client ID is not set."}
    if not doc.fedex_client_secret:
        return {"success": False, "message": "Client Secret is not set."}

    import requests

    from alaiy_os_connector_fedex.fedex.client import FedexClient

    try:
        client = FedexClient()
        client.get_access_token()
        env = "sandbox" if doc.fedex_use_sandbox else "production"
        return {"success": True, "message": f"Connected successfully ({env})."}
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status == 401:
            return {"success": False, "message": "Authentication failed — check your Client ID / Client Secret."}
        body = e.response.text[:200] if e.response is not None else str(e)
        return {"success": False, "message": f"HTTP {status}: {body}"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": "Could not connect to the FedEx API."}
    except requests.exceptions.Timeout:
        return {"success": False, "message": "Request timed out (30s)."}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}
