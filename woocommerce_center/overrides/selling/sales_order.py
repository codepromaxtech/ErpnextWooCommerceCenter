"""
WooCommerce Center — overrides/selling/sales_order.py
Custom Sales Order: conditional autoname for WooCommerce orders + status sync.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Ported and extended from woocommerce_fusion (Starktail).
"""

import json

import frappe
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder
from frappe import _
from frappe.model.naming import get_default_naming_series, make_autoname

from woocommerce_center.tasks.sync_sales_orders import run_sales_order_sync
from woocommerce_center.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
	resolve_wc_server_name,
)


class CustomSalesOrder(SalesOrder):
	"""
	Extends ERPNext's Sales Order to:
	1. Conditionally name WooCommerce-linked orders using server-specific naming series.
	2. Auto-sync WooCommerce order status when ERPNext Sales Order status changes.
	"""

	def autoname(self):
		"""
		If WooCommerce-linked, use WooCommerce Server naming series or default to WEB[idx]-[order_id].
		Otherwise, use normal ERPNext naming.
		"""
		if self.woocommerce_id and self.woocommerce_server:
			wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(self.woocommerce_server))
			if wc_server.sales_order_series:
				self.name = make_autoname(key=wc_server.sales_order_series)
			else:
				wc_servers = frappe.get_all("WooCommerce Server", fields=["name", "creation"])
				sorted_list = sorted(wc_servers, key=lambda server: server.creation)
				# Use the resolved doc name to find the server index
				resolved = wc_server.name
				idx = next(
					(index for (index, d) in enumerate(sorted_list) if d["name"] == resolved),
					0,  # Default to 0 instead of None to avoid TypeError
				)
				self.name = f"WEB{idx + 1}-{int(self.woocommerce_id):06}"
		else:
			naming_series = get_default_naming_series("Sales Order")
			self.name = make_autoname(key=naming_series)

	def on_change(self):
		"""Auto-sync WooCommerce order status based on ERPNext Sales Order status mapping."""
		if self.woocommerce_id and self.woocommerce_server:
			wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(self.woocommerce_server))
			if wc_server.enable_so_status_sync:
				mapping = next(
					(
						row
						for row in wc_server.sales_order_status_map
						if row.erpnext_sales_order_status == self.status
					),
					None,
				)
				if mapping:
					if self.woocommerce_status != mapping.woocommerce_sales_order_status:
						frappe.db.set_value(
							"Sales Order",
							self.name,
							"woocommerce_status",
							mapping.woocommerce_sales_order_status,
						)
						frappe.enqueue(run_sales_order_sync, queue="long", sales_order_name=self.name)


@frappe.whitelist()
def get_woocommerce_order_shipment_trackings(doc: str):
	"""Fetches shipment tracking details from a WooCommerce order."""
	doc = frappe._dict(json.loads(doc))
	if doc.woocommerce_server and doc.woocommerce_id:
		wc_order = get_woocommerce_order(doc.woocommerce_server, doc.woocommerce_id)
		if wc_order.shipment_trackings:
			return json.loads(wc_order.shipment_trackings)
	return []


@frappe.whitelist()
def update_woocommerce_order_shipment_trackings(doc: str, shipment_trackings: list):
	"""Updates the shipment tracking details of a WooCommerce order."""
	doc = frappe._dict(json.loads(doc))
	if doc.woocommerce_server and doc.woocommerce_id:
		wc_order = get_woocommerce_order(doc.woocommerce_server, doc.woocommerce_id)
		wc_order.shipment_trackings = json.dumps(shipment_trackings)
		wc_order.save()
		return wc_order.shipment_trackings
	return None


def get_woocommerce_order(woocommerce_server, woocommerce_id):
	"""Retrieves a WooCommerce order by server and ID."""
	wc_order_name = generate_woocommerce_record_name_from_domain_and_id(woocommerce_server, woocommerce_id)
	wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(woocommerce_server))

	if not wc_server:
		frappe.throw(
			_(
				"This Sales Order is linked to WooCommerce site '{0}', but this site can not be found in 'WooCommerce Servers'"
			).format(woocommerce_server)
		)

	if not wc_server.enable_sync:
		frappe.throw(
			_(
				"This Sales Order is linked to WooCommerce site '{0}', but Synchronisation for this site is disabled in 'WooCommerce Server'"
			).format(woocommerce_server)
		)

	wc_order = frappe.get_doc({"doctype": "WooCommerce Order", "name": wc_order_name})
	wc_order.load_from_db()
	return wc_order
