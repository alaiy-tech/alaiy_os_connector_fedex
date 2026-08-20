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

import time

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

# Retry policy per fedex/rate-limits/fedex-rate-limits.yml: 429 on
# throttle, Retry-After header present.
_RETRYABLE_STATUS = (429, 500, 502, 503, 504)
_MAX_RETRIES = 3
_DEFAULT_RETRY_AFTER_SECONDS = 2


class FedexAPIError(Exception):
    """FedEx API error with the response's own error code/message
    preserved. Error body shape, consistent across all v1 APIs:
      {"errors": [{"code": "...", "message": "..."}], ...}
    retryable=True means every retry attempt was exhausted on a 429/5xx.
    """

    def __init__(self, message, status_code=None, fedex_errors=None, retryable=False):
        super().__init__(message)
        self.status_code = status_code
        self.fedex_errors = fedex_errors or []
        self.retryable = retryable


def _parse_fedex_errors(resp):
    try:
        body = resp.json()
    except ValueError:
        return []
    return body.get("errors") or []


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
        if resp.status_code >= 400:
            fedex_errors = _parse_fedex_errors(resp)
            message = "; ".join(
                f"{e.get('code', '?')}: {e.get('message', '')}" for e in fedex_errors
            ) or f"FedEx OAuth token request returned {resp.status_code}"
            raise FedexAPIError(message, status_code=resp.status_code, fedex_errors=fedex_errors)
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

    def _request(self, method, path, params=None, json=None, timeout=30):
        """Shared by get/post. Retries on 429/5xx honoring Retry-After.
        Raises FedexAPIError with the response body's error code/message
        on terminal failure."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_resp = None
        for attempt in range(_MAX_RETRIES + 1):
            resp = requests.request(
                method, url, headers=self._headers(), params=params, json=json, timeout=timeout,
            )
            if resp.status_code < 400:
                return resp.json()

            last_resp = resp
            if resp.status_code not in _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                break

            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else _DEFAULT_RETRY_AFTER_SECONDS
            time.sleep(wait * (attempt + 1))

        fedex_errors = _parse_fedex_errors(last_resp)
        message = "; ".join(
            f"{e.get('code', '?')}: {e.get('message', '')}" for e in fedex_errors
        ) or f"FedEx API returned {last_resp.status_code} with no parseable error body"
        raise FedexAPIError(
            message,
            status_code=last_resp.status_code,
            fedex_errors=fedex_errors,
            retryable=last_resp.status_code in _RETRYABLE_STATUS,
        )

    def get(self, path, params=None, timeout=30):
        return self._request("GET", path, params=params, timeout=timeout)

    def post(self, path, json=None, timeout=30):
        return self._request("POST", path, json=json, timeout=timeout)

    def put(self, path, json=None, timeout=30):
        return self._request("PUT", path, json=json, timeout=timeout)
