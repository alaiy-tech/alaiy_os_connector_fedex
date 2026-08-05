# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FedExConnectorSettings(Document):
    def validate(self):
        # old_enabled is the last-committed DB value, so this comparison has
        # to run before the save overwrites it. Heavy setup runs only on the
        # 0 -> 1 transition, not on every save.
        old_enabled = frappe.db.get_single_value(
            "FedEx Connector Settings", "is_enabled"
        ) or 0
        self.flags.fedex_just_enabled = bool(self.is_enabled and not old_enabled)
        self.flags.fedex_just_disabled = bool(not self.is_enabled and old_enabled)
        self._sync_registry_is_enabled()
        self._invalidate_cached_token_if_credentials_changed()

    def _invalidate_cached_token_if_credentials_changed(self):
        """Changing Client ID/Secret on the form should never leave a token
        cached under the old credentials -- same fix as Flipkart's client."""
        if self.is_new():
            return
        if self.has_value_changed("fedex_client_id") or self.has_value_changed("fedex_client_secret"):
            self.fedex_access_token = None
            self.fedex_token_expires_at = None

    def on_update(self):
        # Deferred to on_update (after this row is written) so any code that
        # reads back the freshly saved credentials sees the new values.
        if self.flags.fedex_just_enabled:
            self._on_first_enable()
        elif self.flags.fedex_just_disabled:
            self._on_disable()

    def _on_first_enable(self):
        from alaiy_os_connector_fedex.setup.install import setup_custom_fields
        setup_custom_fields()
        # e.g. register webhooks, create default supplier / price lists here.

    def _on_disable(self):
        # e.g. unregister webhooks here.
        pass

    def _sync_registry_is_enabled(self):
        if frappe.db.exists("OS Connector Registry", "fedex"):
            frappe.db.set_value(
                "OS Connector Registry", "fedex", "is_enabled", self.is_enabled
            )
