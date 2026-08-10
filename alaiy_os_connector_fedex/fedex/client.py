# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
FedEx API client — OAuth2 Client Credentials flow.

Confirmed against fedex/openapi/fedex-authorization-api-openapi.yml (raw
YAML read directly, not paraphrased):

  POST {base_url}/oauth/token
  Content-Type: application/x-www-form-urlencoded
  grant_type=client_credentials&client_id=...&client_secret=...

  -> {"access_token": "...", "token_type": "bearer", "expires_in": 3600, "scope": "..."}

Unlike Flipkart (Basic-auth header), FedEx takes client_id/client_secret as
form fields alongside grant_type -- confirmed from the spec's requestBody
schema, not assumed from prose. Token is short-lived (documented 1 hour, not
Flipkart's ~38 days) so it's cached the same way: on FedEx Connector
Settings (fedex_access_token / fedex_token_expires_at), refreshed once
close to expiry rather than per request.
"""

import frappe
import requests
from frappe.utils import add_to_date, now_datetime, get_datetime

PRODUCTION_BASE_URL = "https://apis.fedex.com"
SANDBOX_BASE_URL = "https://apis-sandbox.fedex.com"

TOKEN_PATH = "/oauth/token"
GRANT_TYPE = "client_credentials"

# Refresh this many seconds before the token's real expiry, so a call in
# flight never gets caught using a token that expires mid-request.
_TOKEN_REFRESH_MARGIN_SECONDS = 120


class FedexClient:
    def __init__(self):
        settings = frappe.get_single("FedEx Connector Settings")
        self.client_id = (settings.fedex_client_id or "").strip()
        self.client_secret = (
            settings.get_password("fedex_client_secret")
            if settings.fedex_client_secret else None
        )
        if not self.client_id or not self.client_secret:
            raise RuntimeError("FedEx connector is not configured (Client ID / Client Secret missing).")

        self.base_url = SANDBOX_BASE_URL if settings.fedex_use_sandbox else PRODUCTION_BASE_URL
        self._settings = settings

    # -- Authentication --------------------------------------------------

    def get_access_token(self):
        """Cached token if it's not close to expiry, otherwise fetch a fresh
        one and persist it (so every other worker/request reuses it too)."""
        cached_token = self._settings.get_password("fedex_access_token", raise_exception=False)
        expires_at = self._settings.fedex_token_expires_at
        if cached_token and expires_at and get_datetime(expires_at) > now_datetime():
            return cached_token
        return self._fetch_new_token()

    def _fetch_new_token(self):
        resp = requests.post(
            f"{self.base_url}{TOKEN_PATH}",
            data={
                "grant_type": GRANT_TYPE,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_in = int(data.get("expires_in") or 0)

        expires_at = add_to_date(
            now_datetime(), seconds=max(expires_in - _TOKEN_REFRESH_MARGIN_SECONDS, 0)
        )
        frappe.db.set_single_value("FedEx Connector Settings", "fedex_access_token", token)
        frappe.db.set_single_value("FedEx Connector Settings", "fedex_token_expires_at", expires_at)
        frappe.db.commit()
        self._settings.reload()
        return token

    def _headers(self):
        return {"Authorization": f"Bearer {self.get_access_token()}"}

    # -- Requests ----------------------------------------------------------

    def get(self, path, params=None, timeout=30):
        resp = requests.get(
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            params=params,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def post(self, path, json=None, timeout=30):
        resp = requests.post(
            f"{self.base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            json=json,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
