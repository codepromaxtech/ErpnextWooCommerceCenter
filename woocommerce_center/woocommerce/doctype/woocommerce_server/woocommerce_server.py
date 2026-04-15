"""
WooCommerce Center — WooCommerce Server controller.
Handles autoname, validation, shipment providers, and status mapping.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Ported and extended from woocommerce_fusion (Starktail).
"""

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.caching import redis_cache
from jsonpath_ng.ext import parse
from woocommerce import API

from woocommerce_center.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	WC_ORDER_STATUS_MAPPING,
)
from woocommerce_center.woocommerce.woocommerce_api import parse_domain_from_url




class WooCommerceServer(Document):
	def autoname(self):
		"""Derive name from woocommerce_server_url field."""
		self.name = parse_domain_from_url(self.woocommerce_server_url)

	def validate(self):
		# Auto-prepend https:// if no scheme provided
		url = self.woocommerce_server_url.strip()
		if url and not url.startswith(("http://", "https://")):
			url = "https://" + url
		# Remove trailing slashes
		self.woocommerce_server_url = url.rstrip("/")

		result = urlparse(self.woocommerce_server_url)
		if not all([result.scheme, result.netloc]):
			frappe.throw(_("Please enter a valid WooCommerce Server URL"))

		if self.enable_sync and getattr(self, "wc_plugin_advanced_shipment_tracking", None):
			self.get_shipment_providers()

		if not self.webhook_secret:
			self.webhook_secret = frappe.generate_hash()

		self.validate_so_status_map()
		self.validate_item_map()
		self.validate_reserved_stock_setting()

	def validate_so_status_map(self):
		"""Validate Sales Order Status Map for unique mappings."""
		status_map = getattr(self, "sales_order_status_map", None) or []
		erpnext_so_statuses = [m.erpnext_sales_order_status for m in status_map]
		if len(erpnext_so_statuses) != len(set(erpnext_so_statuses)):
			frappe.throw(_("Duplicate ERPNext Sales Order Statuses found in Sales Order Status Map"))
		wc_so_statuses = [m.woocommerce_sales_order_status for m in status_map]
		if len(wc_so_statuses) != len(set(wc_so_statuses)):
			frappe.throw(_("Duplicate WooCommerce Sales Order Statuses found in Sales Order Status Map"))

	def validate_item_map(self):
		"""Validate Item Field Map for valid JSONPath expressions."""
		disallowed_fields = ["attributes"]
		if self.enable_image_sync:
			disallowed_fields.append("images")

		if self.item_field_map:
			for field_map in self.item_field_map:
				jsonpath_expr = field_map.woocommerce_field_name
				try:
					parse(jsonpath_expr)
				except Exception as e:
					frappe.throw(
						_("Invalid JSONPath syntax in Item Field Map Row {0}:<br><br><pre>{1}</pre>").format(
							field_map.idx, e
						)
					)

				for field in disallowed_fields:
					if field in jsonpath_expr:
						frappe.throw(_("Field '{0}' is not allowed in JSONPath expression").format(field))

	def validate_reserved_stock_setting(self):
		"""Ensure ERPNext stock reservation is enabled when using reserved stock subtraction."""
		if self.subtract_reserved_stock:
			if not frappe.db.get_single_value("Stock Settings", "enable_stock_reservation"):
				frappe.throw(
					_(
						"In order to enable 'Reserved Stock Adjustment', please enable "
						"'Enable Stock Reservation' in 'ERPNext > Stock Settings > Stock Reservation'"
					)
				)

	def get_shipment_providers(self):
		"""Fetch shipment providers from WooCommerce Advanced Shipment Tracking plugin."""
		wc_api = API(
			url=self.woocommerce_server_url,
			consumer_key=self.api_consumer_key,
			consumer_secret=self.get_password("api_consumer_secret"),
			version="wc/v3",
			timeout=40,
			verify_ssl=self.verify_ssl,
		)
		try:
			all_providers = wc_api.get("orders/1/shipment-trackings/providers").json()
			if all_providers:
				provider_names = [provider for country in all_providers for provider in all_providers[country]]
				if hasattr(self, "wc_ast_shipment_providers"):
					self.wc_ast_shipment_providers = "\n".join(provider_names)
		except Exception:
			frappe.log_error("WooCommerce Error", "Failed to fetch shipment providers")

	@frappe.whitelist()
	@redis_cache(ttl=600)
	def get_item_docfields(self, doctype: str) -> list[dict]:
		"""Get DocFields for a doctype, excluding layout fields."""
		invalid_field_types = [
			"Column Break", "Fold", "Heading", "Read Only",
			"Section Break", "Tab Break", "Table", "Table MultiSelect",
		]
		docfields = frappe.get_all(
			"DocField",
			fields=["label", "name", "fieldname"],
			filters=[["fieldtype", "not in", invalid_field_types], ["parent", "=", doctype]],
		)
		custom_fields = frappe.get_all(
			"Custom Field",
			fields=["label", "name", "fieldname"],
			filters=[["fieldtype", "not in", invalid_field_types], ["dt", "=", doctype]],
		)
		return docfields + custom_fields

	@frappe.whitelist()
	@redis_cache(ttl=86400)
	def get_woocommerce_order_status_list(self) -> list[str]:
		"""Retrieve list of WooCommerce Order Statuses."""
		return list(WC_ORDER_STATUS_MAPPING.keys())


@frappe.whitelist()
def get_woocommerce_shipment_providers(woocommerce_server: str):
	"""Return the Shipment Providers for a given WooCommerce Server."""
	wc_server = frappe.get_cached_doc("WooCommerce Server", woocommerce_server)
	return wc_server.wc_ast_shipment_providers
