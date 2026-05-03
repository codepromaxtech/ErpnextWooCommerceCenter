"""
WooCommerce Center — tasks/sync_sales_orders.py
Bidirectional Sales Order ↔ WooCommerce Order synchronisation.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Ported and extended from woocommerce_fusion (Starktail) + woocommerce_integration (ALYF).
"""

import json
from datetime import datetime

import frappe
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder
from erpnext.selling.doctype.sales_order_item.sales_order_item import SalesOrderItem
from frappe import _
from frappe.utils import get_datetime
from frappe.utils.data import add_to_date, cstr, now
from jsonpath_ng.ext import parse

from woocommerce_center.exceptions import SyncDisabledError, WooCommerceOrderNotFoundError
from woocommerce_center.tasks.sync import SynchroniseWooCommerce
from woocommerce_center.tasks.sync_items import run_item_sync
from woocommerce_center.utils import add_tax_details, get_country_name_from_code
from woocommerce_center.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
	resolve_wc_server_name,
)


# ────────────────────────────────────────────────────────────────
# WooCommerce Order Status Mappings (canonical source: woocommerce_order.py)
# ────────────────────────────────────────────────────────────────

from woocommerce_center.woocommerce.doctype.woocommerce_order.woocommerce_order import (
	WC_ORDER_STATUS_MAPPING,
	WC_ORDER_STATUS_MAPPING_REVERSE,
)


# ────────────────────────────────────────────────────────────────
# Hook & Scheduler Entry Points
# ────────────────────────────────────────────────────────────────

def run_sales_order_sync_from_hook(doc, method):
	"""Triggered by doc_events hook on Sales Order submit."""
	if doc.doctype == "Sales Order" and not doc.flags.get("created_by_sync", None) and doc.woocommerce_server:
		frappe.enqueue(run_sales_order_sync, queue="long", sales_order_name=doc.name)


def run_sales_order_sync_from_webhook(order_data: dict, woocommerce_server_name: str):
	"""Called from webhook endpoint when an order is created/updated in WooCommerce."""
	if not order_data or not order_data.get("id"):
		return

	wc_order_name = generate_woocommerce_record_name_from_domain_and_id(
		domain=woocommerce_server_name, resource_id=order_data["id"]
	)
	run_sales_order_sync(woocommerce_order_name=wc_order_name)


def cancel_sales_order_from_webhook(woocommerce_id, woocommerce_server_name: str):
	"""Called from webhook endpoint when an order is deleted in WooCommerce."""
	sales_orders = frappe.get_all(
		"Sales Order",
		filters={"woocommerce_id": str(woocommerce_id), "woocommerce_server": woocommerce_server_name},
		fields=["name", "docstatus"],
	)
	for so in sales_orders:
		if so.docstatus == 1:
			try:
				doc = frappe.get_doc("Sales Order", so.name)
				doc.flags.created_by_sync = True
				doc.cancel()
			except Exception:
				frappe.log_error(
					"WooCommerce Error",
					f"Failed to cancel Sales Order {so.name} from webhook.\n{frappe.get_traceback()}",
				)


@frappe.whitelist()
def run_sales_order_sync(
	sales_order_name: str | None = None,
	sales_order: SalesOrder | None = None,
	woocommerce_order_name: str | None = None,
	woocommerce_order=None,
	enqueue: bool = False,
):
	"""Helper function that prepares arguments for order sync."""
	if not any([sales_order_name, sales_order, woocommerce_order_name, woocommerce_order]):
		raise ValueError(
			"At least one of sales_order_name, sales_order, woocommerce_order_name, woocommerce_order is required"
		)

	sync = None  # Only set when running synchronously (not enqueued)

	if woocommerce_order or woocommerce_order_name:
		if not woocommerce_order:
			woocommerce_order = frappe.get_doc(
				{"doctype": "WooCommerce Order", "name": woocommerce_order_name}
			)
			woocommerce_order.load_from_db()

		if enqueue:
			frappe.enqueue(
				"woocommerce_center.tasks.sync_sales_orders.run_sales_order_sync",
				queue="long",
				woocommerce_order_name=woocommerce_order.name,
			)
		else:
			sync = SynchroniseSalesOrder(woocommerce_order=woocommerce_order)
			sync.run()

	elif sales_order_name or sales_order:
		if not sales_order:
			sales_order = frappe.get_doc("Sales Order", sales_order_name)
		if not sales_order.woocommerce_server:
			frappe.throw(_("No WooCommerce Server defined for Sales Order {0}").format(sales_order_name))
		if enqueue:
			frappe.enqueue(
				"woocommerce_center.tasks.sync_sales_orders.run_sales_order_sync",
				queue="long",
				sales_order_name=sales_order.name,
			)
		else:
			sync = SynchroniseSalesOrder(sales_order=sales_order)
			sync.run()

	return (
		sync.sales_order if sync else None,
		sync.woocommerce_order if sync else None,
	)


@frappe.whitelist()
def sync_woocommerce_orders_modified_since(date_time_from=None):
	"""Hourly scheduler task: get WooCommerce orders modified since last sync date."""
	wc_settings = frappe.get_doc("WooCommerce Integration Settings")

	if not date_time_from:
		date_time_from = getattr(wc_settings, "wc_last_sync_date", None)

	if not date_time_from:
		# First sync — start from epoch to get all orders
		date_time_from = "2000-01-01 00:00:00"

	wc_orders = get_list_of_wc_orders(date_time_from=date_time_from)
	wc_orders += get_list_of_wc_orders(date_time_from=date_time_from, status="trash")
	for wc_order in wc_orders:
		try:
			run_sales_order_sync(woocommerce_order=wc_order, enqueue=True)
		except Exception:
			frappe.log_error(
				"WooCommerce Error",
				f"Failed to sync WooCommerce Order {wc_order.name}\n{frappe.get_traceback()}"
			)

	frappe.db.set_single_value("WooCommerce Integration Settings", "wc_last_sync_date", now())


@frappe.whitelist()
def sync_all_woocommerce_orders():
	"""
	Full sync: enqueue a background job to fetch ALL orders from WooCommerce.
	Returns immediately — the actual sync runs in a background worker.
	"""
	frappe.enqueue(
		"woocommerce_center.tasks.sync_sales_orders._sync_all_woocommerce_orders_job",
		queue="long",
		timeout=7200,  # 2 hours for large order sets
	)
	return "queued"


def _sync_all_woocommerce_orders_job():
	"""Background job: fetch ALL orders and sync each one."""
	wc_orders = get_list_of_wc_orders(date_time_from="2000-01-01 00:00:00")
	wc_orders += get_list_of_wc_orders(date_time_from="2000-01-01 00:00:00", status="trash")
	total = len(wc_orders)
	synced = 0
	errors = 0
	for wc_order in wc_orders:
		try:
			run_sales_order_sync(woocommerce_order=wc_order, enqueue=True)
			synced += 1
		except Exception:
			errors += 1
			frappe.log_error(
				"WooCommerce Error",
				f"Failed to sync WooCommerce Order {wc_order.name}\n{frappe.get_traceback()}"
			)

	frappe.db.set_single_value("WooCommerce Integration Settings", "wc_last_sync_date", now())
	frappe.publish_realtime(
		"msgprint",
		{
			"message": f"Full order sync complete: {total} found, {synced} synced, {errors} errors.",
			"title": "WooCommerce Sync",
			"indicator": "green",
		},
	)


# ────────────────────────────────────────────────────────────────
# Main Synchronisation Class
# ────────────────────────────────────────────────────────────────

class SynchroniseSalesOrder(SynchroniseWooCommerce):
	"""
	Bidirectional sync of WooCommerce Order ↔ ERPNext Sales Order.
	Uses hash-based change detection to prevent sync loops.
	Supports: customer/address creation, payment entries, fee lines, shipping rules, tax sync.
	"""

	def __init__(
		self,
		sales_order: SalesOrder | None = None,
		woocommerce_order=None,
	) -> None:
		super().__init__()
		self.sales_order = sales_order
		self.woocommerce_order = woocommerce_order
		self.settings = frappe.get_cached_doc("WooCommerce Integration Settings")
		self.customer = None

	def run(self):
		"""Run synchronisation."""
		try:
			self.get_corresponding_sales_order_or_woocommerce_order()
			self.sync_wc_order_with_erpnext_order()
		except Exception as err:
			error_message = (
				f"{frappe.get_traceback()}\n\nSales Order Data: \n"
				f"{str(self.sales_order.as_dict()) if self.sales_order else ''}\n\n"
				f"WC Order Data \n{str(self.woocommerce_order.as_dict()) if self.woocommerce_order else ''})"
			)
			frappe.log_error("WooCommerce Error", error_message)
			raise err

	def get_corresponding_sales_order_or_woocommerce_order(self):
		"""Find matching counterpart document."""
		if self.sales_order and not self.woocommerce_order and self.sales_order.woocommerce_id:
			wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(self.sales_order.woocommerce_server))
			if not wc_server.enable_sync:
				raise SyncDisabledError(wc_server)

			wc_orders = get_list_of_wc_orders(sales_order=self.sales_order)
			if len(wc_orders) == 0:
				raise WooCommerceOrderNotFoundError(self.sales_order)
			self.woocommerce_order = wc_orders[0]

		if self.woocommerce_order and not self.sales_order:
			self.get_erpnext_sales_order()

	def get_erpnext_sales_order(self):
		"""Find the ERPNext Sales Order linked to the WooCommerce Order."""
		# The stored woocommerce_server on Sales Order could be either
		# a bare domain or the resolved doc name. Search for both.
		raw_domain = self.woocommerce_order.woocommerce_server
		resolved_name = resolve_wc_server_name(raw_domain)
		server_variants = list({raw_domain, resolved_name})

		filters = [
			["Sales Order", "woocommerce_id", "is", "set"],
			["Sales Order", "woocommerce_server", "is", "set"],
			["Sales Order", "woocommerce_id", "=", self.woocommerce_order.id],
			["Sales Order", "woocommerce_server", "in", server_variants],
		]

		sales_orders = frappe.get_all("Sales Order", filters=filters, fields=["name"])
		if len(sales_orders) > 0:
			self.sales_order = frappe.get_doc("Sales Order", sales_orders[0].name)

	def sync_wc_order_with_erpnext_order(self):
		"""Synchronise Sales Order between ERPNext and WooCommerce."""
		if self.sales_order and not self.woocommerce_order:
			pass  # Creating WC orders from ERPNext is not yet implemented
		elif self.woocommerce_order and not self.sales_order:
			self.create_sales_order(self.woocommerce_order)
		elif self.sales_order and self.woocommerce_order:
			if (
				self.woocommerce_order.woocommerce_date_modified
				!= self.sales_order.custom_woocommerce_last_sync_hash
			):
				if get_datetime(self.woocommerce_order.woocommerce_date_modified) > get_datetime(
					self.sales_order.modified
				):
					self.update_sales_order(self.woocommerce_order, self.sales_order)
				if get_datetime(self.woocommerce_order.woocommerce_date_modified) < get_datetime(
					self.sales_order.modified
				):
					self.update_woocommerce_order(self.woocommerce_order, self.sales_order)

			# Sync Payment Entries for submitted orders
			if (
				self.sales_order.docstatus == 1
				and not self.sales_order.woocommerce_payment_entry
				and not self.sales_order.custom_attempted_woocommerce_auto_payment_entry
			):
				self.sales_order.reload()
				if self.create_and_link_payment_entry(self.woocommerce_order, self.sales_order):
					self.sales_order.save()

	# ── Update ERPNext Sales Order ────────────────

	def update_sales_order(self, woocommerce_order, sales_order: SalesOrder):
		"""Update the ERPNext Sales Order with fields from its WooCommerce Order."""
		if sales_order.docstatus == 2:
			return  # Ignore cancelled orders

		so_dirty = False

		wc_order_status = WC_ORDER_STATUS_MAPPING_REVERSE.get(woocommerce_order.status, woocommerce_order.status)
		if sales_order.woocommerce_status != wc_order_status:
			sales_order.woocommerce_status = wc_order_status
			so_dirty = True

		if sales_order.custom_woocommerce_customer_note != woocommerce_order.customer_note:
			sales_order.custom_woocommerce_customer_note = woocommerce_order.customer_note
			so_dirty = True

		payment_method = (
			woocommerce_order.payment_method_title
			if len(woocommerce_order.payment_method_title or "") < 140
			else woocommerce_order.payment_method
		)
		if sales_order.woocommerce_payment_method != payment_method:
			sales_order.woocommerce_payment_method = payment_method
			so_dirty = True

		if not sales_order.woocommerce_payment_entry:
			if self.create_and_link_payment_entry(woocommerce_order, sales_order):
				so_dirty = True

		if so_dirty:
			sales_order.flags.created_by_sync = True
			sales_order.save()

	# ── Create & Link Payment Entry ────────────────

	def create_and_link_payment_entry(self, wc_order, sales_order: SalesOrder) -> bool:
		"""Create a Payment Entry for a WooCommerce Order marked as paid."""
		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(sales_order.woocommerce_server))
		if not wc_server:
			raise ValueError("Could not find woocommerce_server in list of servers")

		if not (
			wc_server.enable_payments_sync
			and wc_order.payment_method
			and ((wc_server.ignore_date_paid) or (not wc_server.ignore_date_paid and wc_order.date_paid))
			and not sales_order.woocommerce_payment_entry
			and sales_order.docstatus == 1
		):
			return False

		if sales_order.grand_total is None or float(sales_order.grand_total) == 0:
			return True

		payment_method_bank_account_mapping = json.loads(wc_server.payment_method_bank_account_mapping or "{}")
		if wc_order.payment_method not in payment_method_bank_account_mapping:
			raise KeyError(
				f"WooCommerce payment method '{wc_order.payment_method}' not found in WooCommerce Server payment mapping"
			)

		company_bank_account = payment_method_bank_account_mapping[wc_order.payment_method]
		if company_bank_account:
			payment_method_gl_account_mapping = json.loads(wc_server.payment_method_gl_account_mapping or "{}")
			company_gl_account = payment_method_gl_account_mapping[wc_order.payment_method]

			company = frappe.get_value("Account", company_gl_account, "company")
			meta_data = wc_order.get("meta_data", None)

			# Attempt to get transaction ID
			payment_reference_no = wc_order.get("transaction_id", None)
			if not payment_reference_no and meta_data:
				if isinstance(meta_data, str):
					try:
						meta_data = json.loads(meta_data)
					except (json.JSONDecodeError, TypeError):
						meta_data = None
				if isinstance(meta_data, list):
					payment_reference_no = next(
						(data["value"] for data in meta_data if data.get("key") == "yoco_order_payment_id"),
						None,
					)

			# Determine reference (Sales Order or Sales Invoice)
			reference_doctype = "Sales Order"
			reference_name = sales_order.name
			total_amount = sales_order.grand_total
			if sales_order.per_billed > 0:
				si_item_details = frappe.get_all(
					"Sales Invoice Item",
					fields=["name", "parent"],
					filters={"sales_order": sales_order.name},
				)
				if len(si_item_details) > 0:
					reference_doctype = "Sales Invoice"
					reference_name = si_item_details[0].parent
					total_amount = sales_order.grand_total

			payment_entry = frappe.new_doc("Payment Entry")
			payment_entry.update({
				"company": company,
				"payment_type": "Receive",
				"reference_no": payment_reference_no or wc_order.payment_method_title,
				"reference_date": wc_order.date_paid or sales_order.transaction_date,
				"party_type": "Customer",
				"party": sales_order.customer,
				"posting_date": wc_order.date_paid or sales_order.transaction_date,
				"paid_amount": float(wc_order.total),
				"received_amount": float(wc_order.total),
				"bank_account": company_bank_account,
				"paid_to": company_gl_account,
			})
			row = payment_entry.append("references")
			row.reference_doctype = reference_doctype
			row.reference_name = reference_name
			row.total_amount = total_amount
			row.allocated_amount = total_amount
			payment_entry.save()

			sales_order.woocommerce_payment_entry = payment_entry.name

		sales_order.custom_attempted_woocommerce_auto_payment_entry = 1
		return True

	# ── Update WooCommerce Order ────────────────

	def update_woocommerce_order(self, wc_order, sales_order: SalesOrder) -> None:
		"""Update the WooCommerce Order with fields from its ERPNext Sales Order."""
		wc_order_dirty = False

		sales_order_wc_status = (
			WC_ORDER_STATUS_MAPPING.get(sales_order.woocommerce_status)
			if sales_order.woocommerce_status
			else None
		)
		if sales_order_wc_status and sales_order_wc_status != wc_order.status:
			wc_order.status = sales_order_wc_status
			wc_order_dirty = True

		# Update line items if enabled
		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(wc_order.woocommerce_server))
		if getattr(wc_server, "sync_so_items_to_wc", False):
			# Get WooCommerce IDs for items
			raw_domain = wc_order.woocommerce_server
			resolved = resolve_wc_server_name(raw_domain)
			for so_item in sales_order.items:
				so_item.woocommerce_id = frappe.get_value(
					"Item WooCommerce Server",
					filters={
						"parent": so_item.item_code,
						"woocommerce_server": ["in", list({raw_domain, resolved})],
					},
					fieldname="woocommerce_id",
				)

			line_items = json.loads(wc_order.line_items)
			sales_order_items_changed = len(line_items) != len(sales_order.items)

			if not sales_order_items_changed:
				for i, so_item in enumerate(sales_order.items):
					if not so_item.woocommerce_id:
						break
					elif (
						int(so_item.woocommerce_id) != line_items[i]["product_id"]
						or so_item.qty != line_items[i]["quantity"]
						or so_item.rate != get_tax_inc_price_for_woocommerce_line_item(line_items[i])
					):
						sales_order_items_changed = True
						break

			if sales_order_items_changed:
				new_line_items = [
					{
						"product_id": so_item.woocommerce_id,
						"quantity": so_item.qty,
						"price": so_item.rate,
						"meta_data": line_items[i].get("meta_data", []) if i < len(line_items) else [],
					}
					for i, so_item in enumerate(sales_order.items)
				]
				for i, line_item in enumerate(new_line_items):
					self.set_wc_order_line_items_mapped_fields(line_item, sales_order.items[i])

				replacement_line_items = [
					{"id": line_item["id"], "product_id": None}
					for line_item in json.loads(wc_order.line_items)
				]
				replacement_line_items.extend(new_line_items)
				wc_order.line_items = json.dumps(replacement_line_items)
				wc_order_dirty = True

		if wc_order_dirty:
			wc_order.save()

	def set_wc_order_line_items_mapped_fields(self, woocommerce_order_line_item: dict, so_item: SalesOrderItem):
		"""Map ERPNext Sales Order Item fields to WooCommerce order line item fields via JSONPath."""
		if not (woocommerce_order_line_item and self.sales_order and self.woocommerce_order):
			return False, woocommerce_order_line_item

		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(self.woocommerce_order.woocommerce_server))
		if not wc_server.order_line_item_field_map:
			return False, woocommerce_order_line_item

		wc_line_item_dirty = False
		for field_map in wc_server.order_line_item_field_map:
			erpnext_item_field_name = field_map.erpnext_field_name.split(" | ")
			erpnext_item_field_value = getattr(so_item, erpnext_item_field_name[0])

			jsonpath_expr = parse(field_map.woocommerce_field_name)
			woocommerce_order_line_field_matches = jsonpath_expr.find(woocommerce_order_line_item)

			if len(woocommerce_order_line_field_matches) == 0:
				if self.woocommerce_order.name:
					raise ValueError(
						_("Field <code>{0}</code> not found in Item Line of WooCommerce Order {1}").format(
							field_map.woocommerce_field_name, self.woocommerce_order.name,
						)
					)
				continue

			woocommerce_order_line_field_value = woocommerce_order_line_field_matches[0].value
			if erpnext_item_field_value != woocommerce_order_line_field_value:
				jsonpath_expr.update(woocommerce_order_line_item, erpnext_item_field_value)
				wc_line_item_dirty = True

		return wc_line_item_dirty, woocommerce_order_line_item

	# ── Create Sales Order ────────────────

	def create_sales_order(self, wc_order) -> None:
		"""Create an ERPNext Sales Order from the given WooCommerce Order."""
		customer_docname = self.create_or_link_customer_and_address(wc_order)
		self.create_missing_items(wc_order, json.loads(wc_order.line_items), wc_order.woocommerce_server)

		new_sales_order = frappe.new_doc("Sales Order")
		self.sales_order = new_sales_order
		new_sales_order.customer = customer_docname
		new_sales_order.po_no = new_sales_order.woocommerce_id = wc_order.id
		new_sales_order.custom_woocommerce_customer_note = wc_order.customer_note

		new_sales_order.woocommerce_status = WC_ORDER_STATUS_MAPPING_REVERSE.get(
			wc_order.status, wc_order.status
		)
		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(wc_order.woocommerce_server))

		# Store the resolved server document name (not raw domain) so future
		# lookups by woocommerce_server always match the actual doc name.
		new_sales_order.woocommerce_server = wc_server.name
		payment_method = (
			wc_order.payment_method_title
			if len(wc_order.payment_method_title or "") < 140
			else wc_order.payment_method
		)
		new_sales_order.woocommerce_payment_method = payment_method
		created_date = wc_order.date_created.split("T")
		new_sales_order.transaction_date = created_date[0]
		delivery_after = wc_server.delivery_after_days or 7
		new_sales_order.delivery_date = frappe.utils.add_days(created_date[0], delivery_after)
		new_sales_order.company = wc_server.company
		new_sales_order.currency = wc_order.currency

		# Shipping Rule mapping
		if (
			wc_server.enable_shipping_methods_sync
			and (shipping_lines := json.loads(wc_order.shipping_lines or "[]"))
			and len(wc_server.shipping_rule_map) > 0
			and len(shipping_lines) > 0
		):
			shipping_rule_mapping = next(
				(
					rule
					for rule in wc_server.shipping_rule_map
					if rule.wc_shipping_method_id == shipping_lines[0]["method_title"]
				),
				None,
			)
			if shipping_rule_mapping:
				new_sales_order.shipping_rule = shipping_rule_mapping.shipping_rule

		self.set_items_in_sales_order(new_sales_order, wc_order)
		self.set_fee_lines_in_sales_order(new_sales_order, wc_order)
		new_sales_order.flags.ignore_mandatory = True
		new_sales_order.flags.created_by_sync = True
		new_sales_order.insert()
		if wc_server.submit_sales_orders:
			new_sales_order.submit()

		new_sales_order.reload()
		self.create_and_link_payment_entry(wc_order, new_sales_order)
		new_sales_order.save()
		frappe.db.commit()

	# ── Customer & Address ────────────────

	def create_or_link_customer_and_address(self, wc_order) -> str:
		"""Create or update Customer and Address records, with guest order support."""
		raw_billing_data = json.loads(wc_order.billing)
		first_name = raw_billing_data.get("first_name", "").strip()
		last_name = raw_billing_data.get("last_name", "").strip()
		email = raw_billing_data.get("email", "").strip()
		company_name = raw_billing_data.get("company", "").strip()
		individual_name = f"{first_name} {last_name}".strip() or email

		is_guest = wc_order.customer_id is None or wc_order.customer_id == 0
		order_id = wc_order.id
		customer_woo_com_email = raw_billing_data.get("email")

		if not customer_woo_com_email and not is_guest:
			frappe.log_error(
				"WooCommerce Error",
				f"Email is required to create or link a customer.\n\nCustomer Data: {raw_billing_data}",
			)
			return None

		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(wc_order.woocommerce_server))
		if is_guest:
			customer_identifier = f"Guest-{order_id}"
		elif company_name and wc_server.enable_dual_accounts:
			customer_identifier = f"{customer_woo_com_email}-{company_name}"
		else:
			customer_identifier = customer_woo_com_email

		existing_customer = frappe.get_value(
			"Customer", {"woocommerce_identifier": customer_identifier}, "name"
		)

		if not existing_customer:
			customer = frappe.new_doc("Customer")
			customer.woocommerce_identifier = customer_identifier
			customer.customer_type = "Company" if company_name else "Individual"
			customer.woocommerce_is_guest = is_guest
		else:
			customer = frappe.get_doc("Customer", existing_customer)

		customer.customer_name = company_name if company_name else individual_name
		customer.woocommerce_identifier = customer_identifier

		vat_id = raw_billing_data.get("vat_id")
		if isinstance(vat_id, str) and vat_id.strip():
			customer.tax_id = vat_id

		customer.flags.ignore_mandatory = True
		try:
			customer.save()
		except Exception:
			error_message = f"{frappe.get_traceback()}\n\nCustomer Data{customer.as_dict()}"
			frappe.log_error("WooCommerce Error", error_message)
		finally:
			self.customer = customer

		self.create_or_update_address(wc_order)

		contact = find_existing_contact(email, raw_billing_data.get("phone"))
		if not contact:
			contact = create_contact(raw_billing_data, self.customer)

		if contact:
			self.customer.reload()
			self.customer.customer_primary_contact = contact.name
			try:
				self.customer.save()
			except Exception:
				error_message = f"{frappe.get_traceback()}\n\nCustomer Data{customer.as_dict()}"
				frappe.log_error("WooCommerce Error", error_message)

		return customer.name

	# ── Items ────────────────

	def create_missing_items(self, wc_order, items_list, woocommerce_site):
		"""Ensure all products referenced in the order exist as ERPNext Items."""
		for item_data in items_list:
			item_woo_com_id = cstr(item_data.get("variation_id") or item_data.get("product_id"))
			if item_woo_com_id != "0":
				woocommerce_product_name = generate_woocommerce_record_name_from_domain_and_id(
					woocommerce_site, item_woo_com_id
				)
				run_item_sync(woocommerce_product_name=woocommerce_product_name)

	def set_items_in_sales_order(self, new_sales_order, wc_order):
		"""Build Sales Order line items from WooCommerce Order."""
		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(new_sales_order.woocommerce_server))
		if not wc_server.warehouse:
			frappe.throw(_("Please set Warehouse in WooCommerce Server"))

		for item in json.loads(wc_order.line_items):
			woocomm_item_id = item.get("variation_id") or item.get("product_id")

			if woocomm_item_id == 0:
				found_item = create_placeholder_item(new_sales_order)
			else:
				iws = frappe.qb.DocType("Item WooCommerce Server")
				itm = frappe.qb.DocType("Item")
				# Search for both raw domain and resolved doc name
				raw_domain = new_sales_order.woocommerce_server
				resolved = resolve_wc_server_name(raw_domain)
				server_variants = list({raw_domain, resolved})
				item_codes = (
					frappe.qb.from_(iws)
					.join(itm)
					.on(iws.parent == itm.name)
					.where(
						(iws.woocommerce_id == cstr(woocomm_item_id))
						& (iws.woocommerce_server.isin(server_variants))
						& (itm.disabled == 0)
					)
					.select(iws.parent)
					.limit(1)
				).run(as_dict=True)

				found_item = frappe.get_doc("Item", item_codes[0].parent) if item_codes else None

			if not found_item:
				frappe.log_error(
					"WooCommerce Error",
					f"Item with WooCommerce ID {woocomm_item_id} not found for order {wc_order.id}",
				)
				continue

			rate = item.get("price")
			if wc_server.enable_tax_lines_sync and not wc_server.use_actual_tax_type:
				tax_template = frappe.get_cached_doc(
					"Sales Taxes and Charges Template",
					wc_server.sales_taxes_and_charges_template,
				)
				if tax_template.taxes[0].included_in_print_rate:
					rate = get_tax_inc_price_for_woocommerce_line_item(item)

			new_sales_order_line = {
				"item_code": found_item.name,
				"item_name": found_item.item_name,
				"description": found_item.item_name,
				"delivery_date": new_sales_order.delivery_date,
				"qty": item.get("quantity"),
				"rate": rate,
				"warehouse": wc_server.warehouse,
				"discount_percentage": 100 if item.get("price") == 0 else 0,
			}

			self.set_sales_order_item_fields(woocommerce_order_line_item=item, so_item=new_sales_order_line)
			new_sales_order.append("items", new_sales_order_line)

			if wc_server.enable_tax_lines_sync:
				if not wc_server.use_actual_tax_type:
					new_sales_order.taxes_and_charges = wc_server.sales_taxes_and_charges_template
					new_sales_order.set_missing_lead_customer_details()
				else:
					ordered_items_tax = item.get("total_tax")
					add_tax_details(
						new_sales_order, ordered_items_tax, "Ordered Item tax", wc_server.tax_account,
					)

		# Shipping charges and taxes (if no Shipping Rule)
		if not new_sales_order.shipping_rule:
			add_tax_details(new_sales_order, wc_order.shipping_tax, "Shipping Tax", wc_server.f_n_f_tax_account)
			add_tax_details(new_sales_order, wc_order.shipping_total, "Shipping Total", wc_server.f_n_f_account)

		# Handle Woo Orders with no items
		if len(new_sales_order.items) == 0:
			new_sales_order.base_grand_total = float(wc_order.total)
			new_sales_order.grand_total = float(wc_order.total)
			new_sales_order.base_rounded_total = float(wc_order.total)
			new_sales_order.rounded_total = float(wc_order.total)

	def set_fee_lines_in_sales_order(self, new_sales_order, wc_order):
		"""Synchronise Fee Lines from WooCommerce Order to ERPNext Sales Order."""
		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(new_sales_order.woocommerce_server))
		if not wc_server.enable_order_fees_sync:
			return
		if not wc_server.account_for_order_fee_lines:
			frappe.throw(_("Please set 'Account for Order Fee Lines' in WooCommerce Server"))
		if not wc_server.account_for_negative_order_fee_lines:
			frappe.throw(_("Please set 'Account for Negative Order Fee Lines' in WooCommerce Server"))
		if not wc_order.fee_lines:
			return

		for fee_line in json.loads(wc_order.fee_lines):
			new_sales_order.append(
				"taxes",
				{
					"charge_type": "Actual",
					"account_head": wc_server.account_for_order_fee_lines
					if float(fee_line["total"]) > 0
					else wc_server.account_for_negative_order_fee_lines,
					"tax_amount": fee_line["total"],
					"description": fee_line["name"],
				},
			)

			if fee_line.get("tax_status") == "taxable" or len(fee_line.get("taxes", [])) > 0:
				if not wc_server.tax_account_for_order_fee_lines:
					frappe.throw(_("Please set 'Tax Account for Order Fee Lines' in WooCommerce Server"))
				for fee_line_tax in fee_line.get("taxes", []):
					new_sales_order.append(
						"taxes",
						{
							"charge_type": "Actual",
							"account_head": wc_server.tax_account_for_order_fee_lines,
							"tax_amount": fee_line_tax["total"],
							"description": fee_line["name"] + " " + _("Tax"),
						},
					)

	def set_sales_order_item_fields(self, woocommerce_order_line_item: dict, so_item):
		"""Map WooCommerce Order Line Item fields to ERPNext Sales Order Item fields."""
		so_item_dirty = False
		if not (so_item and self.woocommerce_order):
			return so_item_dirty, so_item

		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(self.woocommerce_order.woocommerce_server))
		if not wc_server.order_line_item_field_map:
			return so_item_dirty, so_item

		for field_map in wc_server.order_line_item_field_map:
			erpnext_item_field_name = field_map.erpnext_field_name.split(" | ")
			jsonpath_expr = parse(field_map.woocommerce_field_name)
			woocommerce_order_line_item_field_matches = jsonpath_expr.find(woocommerce_order_line_item)

			if len(woocommerce_order_line_item_field_matches) > 0:
				if isinstance(so_item, dict):
					so_item[erpnext_item_field_name[0]] = woocommerce_order_line_item_field_matches[0].value
				else:
					setattr(so_item, erpnext_item_field_name[0], woocommerce_order_line_item_field_matches[0].value)
					so_item_dirty = True

		return so_item_dirty, so_item

	# ── Address Management ────────────────

	def create_or_update_address(self, wc_order):
		"""Create or update billing and shipping addresses."""
		addresses = get_addresses_linking_to(
			"Customer", self.customer.name,
			fields=["name", "is_primary_address", "is_shipping_address"],
		)

		existing_billing_address = next((addr for addr in addresses if addr.is_primary_address == 1), None)
		existing_shipping_address = next((addr for addr in addresses if addr.is_shipping_address == 1), None)

		raw_billing_data = json.loads(wc_order.billing)
		raw_shipping_data = json.loads(wc_order.shipping)

		address_keys = ["first_name", "last_name", "company", "address_1", "address_2", "city", "state", "postcode", "country"]
		same_address = all(raw_billing_data.get(k) == raw_shipping_data.get(k) for k in address_keys)

		if same_address:
			address = existing_billing_address or existing_shipping_address
			if address:
				self.update_address(address.name, raw_billing_data, self.customer, is_primary_address=1, is_shipping_address=1)
			else:
				self.create_address(raw_billing_data, self.customer, "Billing", is_primary_address=1, is_shipping_address=1)
		else:
			if existing_billing_address:
				self.update_address(existing_billing_address.name, raw_billing_data, self.customer, is_primary_address=1, is_shipping_address=0)
			else:
				self.create_address(raw_billing_data, self.customer, "Billing", is_primary_address=1, is_shipping_address=0)

			if existing_shipping_address:
				self.update_address(existing_shipping_address.name, raw_shipping_data, self.customer, is_primary_address=0, is_shipping_address=1)
			else:
				self.create_address(raw_shipping_data, self.customer, "Shipping", is_primary_address=0, is_shipping_address=1)

	def create_address(self, raw_data: dict, customer, address_type, is_primary_address=0, is_shipping_address=0):
		"""Create a new Address document."""
		address = frappe.new_doc("Address")
		address.address_type = address_type
		address.address_line1 = raw_data.get("address_1", "Not Provided")
		address.address_line2 = raw_data.get("address_2", "")
		address.city = raw_data.get("city", "Not Provided")
		address.country = get_country_name_from_code(raw_data.get("country", "")) or "Bangladesh"
		address.state = raw_data.get("state")
		address.pincode = raw_data.get("postcode")
		address.phone = raw_data.get("phone")
		address.address_title = f"{customer.name}-{address_type}"
		address.is_primary_address = is_primary_address
		address.is_shipping_address = is_shipping_address
		address.append("links", {"link_doctype": "Customer", "link_name": customer.name})
		address.flags.ignore_mandatory = True
		address.save()

	def update_address(self, address_name, raw_data: dict, customer, is_primary_address=0, is_shipping_address=0):
		"""Update an existing Address document."""
		address = frappe.get_doc("Address", address_name)
		address.address_line1 = raw_data.get("address_1", "Not Provided")
		address.address_line2 = raw_data.get("address_2", "")
		address.city = raw_data.get("city", "Not Provided")
		address.country = get_country_name_from_code(raw_data.get("country", "")) or "Bangladesh"
		address.state = raw_data.get("state")
		address.pincode = raw_data.get("postcode")
		address.phone = raw_data.get("phone")
		address.is_primary_address = is_primary_address
		address.is_shipping_address = is_shipping_address
		address.flags.ignore_mandatory = True
		address.save()


# ────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────

def get_list_of_wc_orders(
	date_time_from: datetime | None = None,
	sales_order: SalesOrder | None = None,
	status: str | None = None,
) -> list:
	"""Fetch WooCommerce Orders with pagination."""
	if not any([date_time_from, sales_order]):
		raise ValueError("At least one of date_time_from or sales_order parameters are required")

	wc_records_per_page_limit = 100
	page_length = wc_records_per_page_limit
	new_results = True
	start = 0
	filters = []
	wc_orders = []

	wc_settings = frappe.get_cached_doc("WooCommerce Integration Settings")
	minimum_creation_date = getattr(wc_settings, "minimum_creation_date", None)

	if date_time_from:
		filters.append(["WooCommerce Order", "date_modified", ">", date_time_from])
	if minimum_creation_date:
		filters.append(["WooCommerce Order", "date_created", ">", minimum_creation_date])
	if sales_order:
		filters.append(["WooCommerce Order", "id", "=", sales_order.woocommerce_id])
	if status:
		filters.append(["WooCommerce Order", "status", "=", status])

	while new_results:
		woocommerce_order = frappe.get_doc({"doctype": "WooCommerce Order"})
		new_results = woocommerce_order.get_list(
			args={
				"filters": filters,
				"page_length": page_length,
				"start": start,
				"as_doc": True,
			}
		)
		for wc_order in new_results:
			wc_orders.append(wc_order)
		start += page_length
		if len(new_results) < page_length:
			new_results = []

	return wc_orders


def find_existing_contact(email, phone):
	"""Find an existing Contact by email or phone."""
	if email:
		existing = frappe.db.get_value("Contact Email", {"email_id": email}, "parent")
		if existing:
			return frappe._dict({"name": existing})
	if phone:
		existing = frappe.db.get_value("Contact Phone", {"phone": phone}, "parent")
		if existing:
			return frappe._dict({"name": existing})
	return None


def create_contact(data, customer):
	"""Create a new Contact linked to the Customer."""
	email = data.get("email", None)
	phone = data.get("phone", None)

	if not email and not phone:
		return None

	contact = frappe.new_doc("Contact")
	contact.first_name = data.get("first_name")
	contact.last_name = data.get("last_name")
	contact.is_primary_contact = 1
	contact.is_billing_contact = 1

	if phone:
		contact.add_phone(phone, is_primary_mobile_no=1, is_primary_phone=1)
	if email:
		contact.add_email(email, is_primary=1)

	contact.append("links", {"link_doctype": "Customer", "link_name": customer.name})
	contact.flags.ignore_mandatory = True
	contact.save()
	return contact


def add_tax_details(sales_order, price, desc, tax_account_head):
	"""Append a tax/charge row to the Sales Order."""
	if not price or not tax_account_head:
		return
	sales_order.append(
		"taxes",
		{
			"charge_type": "Actual",
			"account_head": tax_account_head,
			"tax_amount": price,
			"description": desc,
		},
	)


def get_tax_inc_price_for_woocommerce_line_item(line_item: dict):
	"""Calculate the tax-inclusive rate for a WooCommerce line item."""
	return (float(line_item.get("subtotal", 0)) + float(line_item.get("subtotal_tax", 0))) / max(
		float(line_item.get("quantity", 1)), 1
	)


def create_placeholder_item(sales_order: SalesOrder):
	"""Create a placeholder Item for deleted WooCommerce Products."""
	wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(sales_order.woocommerce_server))
	if not frappe.db.exists("Item", "DELETED_WOOCOMMERCE_PRODUCT"):
		item = frappe.new_doc("Item")
		item.item_code = "DELETED_WOOCOMMERCE_PRODUCT"
		item.item_name = "Deleted WooCommerce Product"
		item.description = "Deleted WooCommerce Product"
		item.item_group = "All Item Groups"
		item.stock_uom = wc_server.uom or "Nos"
		item.is_stock_item = 0
		item.is_fixed_asset = 0
		item.opening_stock = 0
		item.flags.created_by_sync = True
		item.save()
	else:
		item = frappe.get_doc("Item", "DELETED_WOOCOMMERCE_PRODUCT")
	return item


def get_addresses_linking_to(doctype, docname, fields=None):
	"""Return Addresses containing a link to the given document."""
	return frappe.get_all(
		"Address",
		fields=fields,
		filters=[
			["Dynamic Link", "link_doctype", "=", doctype],
			["Dynamic Link", "link_name", "=", docname],
		],
	)
