"""
WooCommerce Center — tasks/stock_update.py
Pushes ERPNext stock levels to WooCommerce.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Ported and extended from woocommerce_fusion (Starktail).
"""

import math

import frappe

from woocommerce_center.tasks.utils import APIWithRequestLogging




def update_stock_levels_for_woocommerce_item(doc, method):
	"""
	Triggered by doc_events on Stock Entry, Stock Reconciliation,
	Sales Invoice (with update_stock), and Delivery Note.
	Enqueues stock level updates for each item to WooCommerce.
	"""
	if frappe.flags.in_test:
		return

	if doc.doctype not in ("Stock Entry", "Stock Reconciliation", "Sales Invoice", "Delivery Note"):
		return

	# Check if there are any enabled WooCommerce Servers with stock sync enabled
	if not frappe.get_list(
		"WooCommerce Server",
		filters={"enable_sync": 1, "enable_stock_level_synchronisation": 1},
		limit=1,
	):
		return

	# Sales Invoice only triggers stock update if update_stock is enabled
	if doc.doctype == "Sales Invoice" and not doc.update_stock:
		return

	item_codes = [row.item_code for row in doc.items]
	for item_code in item_codes:
		frappe.enqueue(
			"woocommerce_center.tasks.stock_update.update_stock_levels_on_woocommerce_site",
			enqueue_after_commit=True,
			item_code=item_code,
		)


@frappe.whitelist()
def update_stock_levels_for_all_enabled_items_in_background():
	"""
	Daily scheduler task: get all enabled ERPNext Items and post stock updates to WooCommerce.
	"""
	erpnext_items = []
	current_page_length = 500
	start = 0

	while current_page_length == 500:
		items = frappe.db.get_all(
			doctype="Item",
			filters={"disabled": 0},
			fields=["name"],
			start=start,
			page_length=500,
		)
		erpnext_items.extend(items)
		current_page_length = len(items)
		start += current_page_length

	for item in erpnext_items:
		frappe.enqueue(
			"woocommerce_center.tasks.stock_update.update_stock_levels_on_woocommerce_site",
			item_code=item.name,
		)


@frappe.whitelist()
def update_stock_levels_on_woocommerce_site(item_code: str):
	"""
	Updates stock levels of an item on all its associated WooCommerce sites.
	Calculates stock from configured warehouses, handles variants, and supports
	reserved stock subtraction.
	"""
	item = frappe.get_doc("Item", item_code)

	if len(item.woocommerce_servers) == 0 or not item.is_stock_item or item.disabled:
		return False

	bins = frappe.get_list(
		"Bin", {"item_code": item_code}, ["name", "warehouse", "reserved_qty", "actual_qty"]
	)

	for wc_site in item.woocommerce_servers:
		if not wc_site.woocommerce_id:
			continue

		woocommerce_id = wc_site.woocommerce_id
		woocommerce_server = wc_site.woocommerce_server
		wc_server = frappe.get_cached_doc("WooCommerce Server", woocommerce_server)

		if (
			not wc_server
			or not wc_server.enable_sync
			or not wc_site.enabled
			or not wc_server.enable_stock_level_synchronisation
		):
			continue

		wc_api = APIWithRequestLogging(
			url=wc_server.woocommerce_server_url,
			consumer_key=wc_server.api_consumer_key,
			consumer_secret=wc_server.get_password("api_consumer_secret"),
			version="wc/v3",
			timeout=40,
			verify_ssl=bool(wc_server.verify_ssl),
		)

		# Sum quantities from configured warehouses, round down (WC API doesn't accept floats)
		configured_warehouses = [row.warehouse for row in wc_server.warehouses]
		data_to_post = {
			"stock_quantity": math.floor(
				sum(
					bin.actual_qty if not wc_server.subtract_reserved_stock else bin.actual_qty - bin.reserved_qty
					for bin in bins
					if bin.warehouse in configured_warehouses
				)
			)
		}

		try:
			# Handle product variants — use variation endpoint
			parent_woocommerce_id = None
			if item.variant_of:
				parent_item = frappe.get_doc("Item", item.variant_of)
				for parent_wc_site in parent_item.woocommerce_servers:
					if parent_wc_site.woocommerce_server == woocommerce_server:
						parent_woocommerce_id = parent_wc_site.woocommerce_id
						break
				if not parent_woocommerce_id:
					continue
				endpoint = f"products/{parent_woocommerce_id}/variations/{woocommerce_id}"
			else:
				endpoint = f"products/{woocommerce_id}"

			response = wc_api.put(endpoint=endpoint, data=data_to_post)
		except Exception as err:
			error_message = f"{frappe.get_traceback()}\n\nData in PUT request: \n{data_to_post}"
			frappe.log_error("WooCommerce Error", error_message)
			raise err

		if response.status_code != 200:
			error_message = (
				f"Status Code not 200\n\nData in PUT request: \n{data_to_post}"
				f"\n\nResponse: \n{response.status_code}"
				f"\nResponse Text: {response.text}"
				f"\nRequest URL: {response.request.url}"
				f"\nRequest Body: {response.request.body}"
			)
			frappe.log_error("WooCommerce Error", error_message)
			raise ValueError(error_message)

	return True
