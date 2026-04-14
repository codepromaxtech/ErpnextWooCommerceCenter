"""
WooCommerce Center — WooCommerce Order controller.
Virtual doctype backed by WooCommerce REST API.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Ported and extended from woocommerce_fusion (Starktail).
"""

import json
from dataclasses import dataclass
from datetime import datetime

import frappe

from woocommerce_center.tasks.utils import APIWithRequestLogging
from woocommerce_center.woocommerce.woocommerce_api import (
	WooCommerceAPI,
	WooCommerceResource,
	get_domain_and_id_from_woocommerce_record_name,
	log_and_raise_error,
)

WC_ORDER_DELIMITER = "~"

# Canonical WooCommerce order status mapping
# This lives here (not in tasks/sync_sales_orders.py) to avoid circular imports
# when woocommerce_server.py needs it.
WC_ORDER_STATUS_MAPPING = {
	"Pending Payment": "pending",
	"On hold": "on-hold",
	"Failed": "failed",
	"Cancelled": "cancelled",
	"Processing": "processing",
	"Refunded": "refunded",
	"Shipped": "completed",
	"Ready for Pickup": "ready-pickup",
	"Picked up": "pickup",
	"Delivered": "completed",
	"Processing LP": "processing-lp",
	"Dispatched Pickup": "dispatched-pickup",
	"Draft": "checkout-draft",
	"Quote Sent": "quote-sent",
	"Trash": "trash",
	"Partially Shipped": "partial-shipped",
}

WC_ORDER_STATUS_MAPPING_REVERSE = {v: k for k, v in WC_ORDER_STATUS_MAPPING.items()}




@dataclass
class WooCommerceOrderAPI(WooCommerceAPI):
	"""Extended API config for orders with shipment tracking plugin support."""
	wc_plugin_advanced_shipment_tracking: bool = False


class WooCommerceOrder(WooCommerceResource):
	"""Virtual doctype for WooCommerce Orders."""

	doctype = "WooCommerce Order"
	resource: str = "orders"

	@staticmethod
	def _init_api() -> list[WooCommerceAPI]:
		"""Initialise the WooCommerce API for all enabled servers."""
		wc_servers = frappe.get_all("WooCommerce Server")
		wc_servers = [frappe.get_doc("WooCommerce Server", server.name) for server in wc_servers]

		wc_api_list = [
			WooCommerceOrderAPI(
				api=APIWithRequestLogging(
					url=server.woocommerce_server_url,
					consumer_key=server.api_consumer_key,
					consumer_secret=server.api_consumer_secret,
					version="wc/v3",
					timeout=40,
					verify_ssl=server.verify_ssl,
				),
				woocommerce_server_url=server.woocommerce_server_url,
				woocommerce_server=server.name,
				wc_plugin_advanced_shipment_tracking=server.wc_plugin_advanced_shipment_tracking,
			)
			for server in wc_servers
			if server.enable_sync == 1
		]

		return wc_api_list

	@staticmethod
	def get_list(args):
		return WooCommerceOrder.get_list_of_records(args)

	def after_load_from_db(self, order: dict):
		return self.get_additional_order_attributes(order)

	@staticmethod
	def get_count(args) -> int:
		return WooCommerceOrder.get_count_of_records(args)

	def before_db_update(self, order: dict):
		# Drop all fields except for 'status', 'shipment_trackings' and 'line_items'
		keys_to_pop = [
			key for key in order.keys() if key not in ("status", "shipment_trackings", "line_items")
		]
		for key in keys_to_pop:
			order.pop(key)
		return order

	def after_db_update(self):
		self.update_shipment_tracking()

	def get_additional_order_attributes(self, order: dict):
		"""Get additional order attributes (e.g. shipment tracking from AST plugin)."""
		if self.current_wc_api:
			if self.current_wc_api.wc_plugin_advanced_shipment_tracking:
				_wc_server_domain, order_id = get_domain_and_id_from_woocommerce_record_name(self.name)
				try:
					order["shipment_trackings"] = self.current_wc_api.api.get(
						f"orders/{order_id}/shipment-trackings"
					).json()

					# Fix broken date_shipped from /shipment-trackings endpoint
					if "meta_data" in order:
						shipment_trackings_meta_data = next(
							(
								entry
								for entry in json.loads(order["meta_data"])
								if entry["key"] == "_wc_shipment_tracking_items"
							),
							None,
						)
						if shipment_trackings_meta_data:
							for shipment_tracking in order["shipment_trackings"]:
								shipment_tracking_meta_data = next(
									(
										entry
										for entry in shipment_trackings_meta_data["value"]
										if entry["tracking_id"] == shipment_tracking["tracking_id"]
									),
									None,
								)
								if shipment_tracking_meta_data:
									date_shipped = datetime.fromtimestamp(
										int(shipment_tracking_meta_data["date_shipped"])
									)
									shipment_tracking["date_shipped"] = date_shipped.strftime("%Y-%m-%d")

					order["shipment_trackings"] = json.dumps(order["shipment_trackings"])

				except Exception as err:
					log_and_raise_error(err)

		return order

	def update_shipment_tracking(self):
		"""Handle Advanced Shipment Tracking WooCommerce plugin updates."""
		if not self.wc_api_list:
			self.init_api()

		wc_server_domain, order_id = get_domain_and_id_from_woocommerce_record_name(self.name)
		self.current_wc_api = next(
			(api for api in self.wc_api_list if wc_server_domain in api.woocommerce_server_url), None
		)

		if self.current_wc_api.wc_plugin_advanced_shipment_tracking and self.shipment_trackings:
			if self.shipment_trackings != self._doc_before_save.shipment_trackings:
				new_shipment_tracking = json.loads(self.shipment_trackings)

				for item in new_shipment_tracking:
					if "tracking_id" in item:
						item.pop("tracking_id")

				tracking_info = new_shipment_tracking[0]
				tracking_info["replace_tracking"] = 1

				try:
					response = self.current_wc_api.api.post(
						f"orders/{order_id}/shipment-trackings/", data=tracking_info
					)
				except Exception as err:
					log_and_raise_error(err, error_text="update_shipment_tracking failed")
				if response.status_code != 201:
					log_and_raise_error(error_text="update_shipment_tracking failed", response=response)
