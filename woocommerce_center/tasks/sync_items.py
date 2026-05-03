"""
WooCommerce Center — tasks/sync_items.py
Bidirectional Item ↔ WooCommerce Product synchronisation.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Ported and extended from woocommerce_fusion (Starktail) + ErpnextWooCommerceConnector (libracore).
"""

import json
from dataclasses import dataclass
from datetime import datetime

import frappe
from erpnext.stock.doctype.item.item import Item
from frappe import ValidationError, _, _dict
from frappe.query_builder import Criterion
from frappe.utils import add_to_date, get_datetime, now
from jsonpath_ng.ext import parse

from woocommerce_center.exceptions import SyncDisabledError
from woocommerce_center.tasks.sync import SynchroniseWooCommerce
from woocommerce_center.woocommerce.woocommerce_api import (
	generate_woocommerce_record_name_from_domain_and_id,
	resolve_wc_server_name,
)


def _safe_abbr(value: str, max_len: int = 30) -> str:
	"""
	Generate a safe ERPNext Item Attribute abbreviation.
	ERPNext's `abbr` field is limited to 30 characters.
	We strip spaces and truncate to avoid DB validation errors from long option values
	(e.g. 'Wash with gentle soap, not detergent' → 30-char abbr).
	"""
	return value.replace(" ", "")[:max_len]


# ────────────────────────────────────────────────────────────────
# Hook & Scheduler Entry Points
# ────────────────────────────────────────────────────────────────

def run_item_sync_from_hook(doc, method):
	"""
	Triggered by a Document Controller hook from Item.
	Enqueues a background sync for any item linked to WooCommerce servers.
	"""
	if (
		doc.doctype == "Item"
		and not doc.flags.get("created_by_sync", None)
		and len(doc.woocommerce_servers) > 0
	):
		frappe.msgprint(
			_("Background sync to WooCommerce triggered for {0} {1}").format(frappe.bold(doc.name), method),
			indicator="blue",
			alert=True,
		)
		frappe.enqueue(clear_sync_hash_and_run_item_sync, item_code=doc.name)


def run_item_sync_from_webhook(product_data: dict, woocommerce_server_name: str):
	"""
	Called from webhook endpoint when a product is created/updated in WooCommerce.
	"""
	if not product_data or not product_data.get("id"):
		return

	wc_product_name = generate_woocommerce_record_name_from_domain_and_id(
		domain=woocommerce_server_name, resource_id=product_data["id"]
	)
	run_item_sync(woocommerce_product_name=wc_product_name)


@frappe.whitelist()
def run_item_sync(
	item_code: str | None = None,
	item: Item | None = None,
	woocommerce_product_name: str | None = None,
	woocommerce_product=None,
	enqueue: bool = False,
):
	"""
	Helper function that prepares arguments for item sync.
	At least one of the parameters must be provided.
	"""
	if not any([item_code, item, woocommerce_product_name, woocommerce_product]):
		raise ValueError(
			"At least one of item_code, item, woocommerce_product_name, woocommerce_product parameters required"
		)

	sync = None

	if woocommerce_product or woocommerce_product_name:
		if not woocommerce_product:
			woocommerce_product = frappe.get_doc(
				{"doctype": "WooCommerce Product", "name": woocommerce_product_name}
			)
			woocommerce_product.load_from_db()

		sync = SynchroniseItem(woocommerce_product=woocommerce_product)
		if enqueue:
			frappe.enqueue(sync.run)
		else:
			sync.run()

	elif item or item_code:
		if not item:
			item = frappe.get_doc("Item", item_code)
		if not item.woocommerce_servers:
			frappe.throw(_("No WooCommerce Servers defined for Item {0}").format(item_code))
		for wc_server in item.woocommerce_servers:
			sync = SynchroniseItem(
				item=ERPNextItemToSync(item=item, item_woocommerce_server_idx=wc_server.idx)
			)
			if enqueue:
				frappe.enqueue(sync.run)
			else:
				sync.run()

	return (
		sync.item.item if sync and sync.item else None,
		sync.woocommerce_product if sync else None,
	)


@frappe.whitelist()
def sync_woocommerce_products_modified_since(date_time_from=None):
	"""
	Hourly scheduler task: get WooCommerce products modified since last sync date.
	"""
	wc_settings = frappe.get_doc("WooCommerce Integration Settings")

	if not date_time_from:
		date_time_from = getattr(wc_settings, "wc_last_sync_date_items", None)

	if not date_time_from:
		# First sync — start from epoch to get all products
		date_time_from = "2000-01-01 00:00:00"

	wc_products = get_list_of_wc_products(date_time_from=date_time_from)
	for wc_product in wc_products:
		try:
			run_item_sync(woocommerce_product=wc_product, enqueue=True)
		except Exception:
			pass  # Skip items with errors — exceptions are logged

	frappe.db.set_single_value("WooCommerce Integration Settings", "wc_last_sync_date_items", now())


@frappe.whitelist()
def sync_all_woocommerce_products():
	"""
	Full sync: enqueue a background job to fetch ALL products from WooCommerce.
	Returns immediately — the actual sync runs in a background worker.
	"""
	frappe.enqueue(
		"woocommerce_center.tasks.sync_items._sync_all_woocommerce_products_job",
		queue="long",
		timeout=7200,  # 2 hours for large catalogs
	)
	return "queued"


def _sync_all_woocommerce_products_job():
	"""Background job: fetch ALL products and sync each one."""
	wc_products = get_list_of_wc_products()
	total = len(wc_products)
	synced = 0
	errors = 0
	for wc_product in wc_products:
		try:
			run_item_sync(woocommerce_product=wc_product, enqueue=True)
			synced += 1
		except Exception:
			errors += 1

	frappe.db.set_single_value("WooCommerce Integration Settings", "wc_last_sync_date_items", now())
	frappe.publish_realtime(
		"msgprint",
		{
			"message": f"Full product sync complete: {total} found, {synced} synced, {errors} errors.",
			"title": "WooCommerce Sync",
			"indicator": "green",
		},
	)


# ────────────────────────────────────────────────────────────────
# Data Classes
# ────────────────────────────────────────────────────────────────

@dataclass
class ERPNextItemToSync:
	"""Tracks an ERPNext Item and the relevant WooCommerce Server to sync to."""

	item: Item
	item_woocommerce_server_idx: int

	@property
	def item_woocommerce_server(self):
		return self.item.woocommerce_servers[self.item_woocommerce_server_idx - 1]


# ────────────────────────────────────────────────────────────────
# Main Synchronisation Class
# ────────────────────────────────────────────────────────────────

class SynchroniseItem(SynchroniseWooCommerce):
	"""
	Class for managing bidirectional synchronisation of WooCommerce Product ↔ ERPNext Item.
	Uses hash-based change detection to prevent sync loops.
	"""

	def __init__(
		self,
		servers=None,
		item: ERPNextItemToSync | None = None,
		woocommerce_product=None,
	) -> None:
		super().__init__(servers)
		self.item = item
		self.woocommerce_product = woocommerce_product
		self.settings = frappe.get_cached_doc("WooCommerce Integration Settings")

	def run(self):
		"""Run synchronisation."""
		try:
			self.get_corresponding_item_or_product()
			self.sync_wc_product_with_erpnext_item()
		except Exception as err:
			try:
				woocommerce_product_dict = (
					self.woocommerce_product.as_dict()
					if hasattr(self.woocommerce_product, "as_dict")
					else self.woocommerce_product
				)
			except ValidationError:
				woocommerce_product_dict = self.woocommerce_product
			error_message = (
				f"{frappe.get_traceback()}\n\nItem Data: \n"
				f"{str(self.item) if self.item else ''}\n\n"
				f"WC Product Data \n{str(woocommerce_product_dict) if self.woocommerce_product else ''})"
			)
			frappe.log_error("WooCommerce Error", error_message)
			raise err

	def get_corresponding_item_or_product(self):
		"""
		If we have an ERPNext Item, get the corresponding WooCommerce Product.
		If we have a WooCommerce Product, get the corresponding ERPNext Item.
		"""
		if self.item and not self.woocommerce_product and self.item.item_woocommerce_server.woocommerce_id:
			wc_server = frappe.get_cached_doc(
				"WooCommerce Server", resolve_wc_server_name(self.item.item_woocommerce_server.woocommerce_server)
			)
			if not wc_server.enable_sync:
				raise SyncDisabledError(wc_server)

			wc_products = get_list_of_wc_products(item=self.item)
			if len(wc_products) == 0:
				raise ValueError(
					f"No WooCommerce Product found with ID {self.item.item_woocommerce_server.woocommerce_id} "
					f"on {self.item.item_woocommerce_server.woocommerce_server}"
				)
			self.woocommerce_product = wc_products[0]

		if self.woocommerce_product and not self.item:
			self.get_erpnext_item()

	def get_erpnext_item(self):
		"""Get ERPNext Item for a WooCommerce Product."""
		if not all([self.woocommerce_product.woocommerce_server, self.woocommerce_product.woocommerce_id]):
			raise ValueError("Both woocommerce_server and woocommerce_id required")

		iws = frappe.qb.DocType("Item WooCommerce Server")
		itm = frappe.qb.DocType("Item")

		# The stored woocommerce_server on Item WooCommerce Server could be either
		# a bare domain ('yoursite.com') or the resolved doc name ('https://yoursite.com').
		# Search for both to handle legacy data.
		raw_domain = self.woocommerce_product.woocommerce_server
		resolved_name = resolve_wc_server_name(raw_domain)
		server_variants = list({raw_domain, resolved_name})  # deduplicate if same

		and_conditions = [
			iws.woocommerce_server.isin(server_variants),
			iws.woocommerce_id == self.woocommerce_product.woocommerce_id,
		]

		item_codes = (
			frappe.qb.from_(iws)
			.join(itm)
			.on(iws.parent == itm.name)
			.where(Criterion.all(and_conditions))
			.select(iws.parent, iws.name)
			.limit(1)
		).run(as_dict=True)

		found_item = frappe.get_doc("Item", item_codes[0].parent) if item_codes else None
		if found_item:
			self.item = ERPNextItemToSync(
				item=found_item,
				item_woocommerce_server_idx=next(
					server.idx
					for server in found_item.woocommerce_servers
					if server.name == item_codes[0].name
				),
			)

	def sync_wc_product_with_erpnext_item(self):
		"""Synchronise Item between ERPNext and WooCommerce."""
		if self.item and not self.woocommerce_product:
			self.create_woocommerce_product(self.item)
		elif self.woocommerce_product and not self.item:
			self.create_item(self.woocommerce_product)
		elif self.item and self.woocommerce_product:
			if (
				self.woocommerce_product.woocommerce_date_modified
				!= self.item.item_woocommerce_server.woocommerce_last_sync_hash
			):
				if get_datetime(self.woocommerce_product.woocommerce_date_modified) > get_datetime(
					self.item.item.modified
				):
					self.update_item(self.woocommerce_product, self.item)
				if get_datetime(self.woocommerce_product.woocommerce_date_modified) < get_datetime(
					self.item.item.modified
				):
					self.update_woocommerce_product(self.woocommerce_product, self.item)

	def update_item(self, woocommerce_product, item: ERPNextItemToSync):
		"""Update the ERPNext Item with fields from its corresponding WooCommerce Product."""
		item_dirty = False
		if item.item.item_name != woocommerce_product.woocommerce_name:
			item.item.item_name = woocommerce_product.woocommerce_name
			item_dirty = True

		fields_updated, item.item = self.set_item_fields(item=item.item)

		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(woocommerce_product.woocommerce_server))
		if wc_server.enable_image_sync:
			wc_product_images = json.loads(woocommerce_product.images)
			if len(wc_product_images) > 0:
				if item.item.image != wc_product_images[0]["src"]:
					item.item.image = wc_product_images[0]["src"]
					item_dirty = True

		if item_dirty or fields_updated:
			item.item.flags.created_by_sync = True
			item.item.save()

		self.set_sync_hash()

	def update_woocommerce_product(self, wc_product, item: ERPNextItemToSync) -> None:
		"""Update the WooCommerce Product with fields from its corresponding ERPNext Item."""
		wc_product_dirty = False

		if wc_product.woocommerce_name != item.item.item_name:
			wc_product.woocommerce_name = item.item.item_name
			wc_product_dirty = True

		product_fields_changed, wc_product = self.set_product_fields(wc_product, item)
		if product_fields_changed:
			wc_product_dirty = True

		if wc_product_dirty:
			wc_product.save()

		self.woocommerce_product = wc_product
		self.set_sync_hash()

	def create_woocommerce_product(self, item: ERPNextItemToSync) -> None:
		"""Create a WooCommerce Product from its corresponding ERPNext Item."""
		if (
			item.item_woocommerce_server.woocommerce_server
			and item.item_woocommerce_server.enabled
			and not item.item_woocommerce_server.woocommerce_id
		):
			wc_product = frappe.get_doc({"doctype": "WooCommerce Product"})
			wc_product.type = "simple"

			# Handle variants
			if item.item.has_variants:
				wc_product.type = "variable"
				wc_product_attributes = []
				for row in item.item.attributes:
					item_attribute = frappe.get_doc("Item Attribute", row.attribute)
					wc_product_attributes.append(
						{
							"name": row.attribute,
							"slug": row.attribute.lower().replace(" ", "_"),
							"visible": True,
							"variation": True,
							"options": [
								option.attribute_value for option in item_attribute.item_attribute_values
							],
						}
					)
				wc_product.attributes = json.dumps(wc_product_attributes)

			if item.item.variant_of:
				parent_item = frappe.get_doc("Item", item.item.variant_of)
				parent_item, parent_wc_product = run_item_sync(item_code=parent_item.item_code)
				wc_product.parent_id = parent_wc_product.woocommerce_id
				wc_product.type = "variation"

				wc_product_attributes = [
					{
						"name": row.attribute,
						"slug": row.attribute.lower().replace(" ", "_"),
						"option": row.attribute_value,
					}
					for row in item.item.attributes
				]
				wc_product.attributes = json.dumps(wc_product_attributes)

			wc_product.woocommerce_server = item.item_woocommerce_server.woocommerce_server
			wc_product.woocommerce_name = item.item.item_name
			wc_product.regular_price = get_item_price_rate(item) or "0"

			self.set_product_fields(wc_product, item)
			wc_product.insert()
			self.woocommerce_product = wc_product

			item.item.reload()
			item.item_woocommerce_server.woocommerce_id = wc_product.woocommerce_id
			item.item.flags.created_by_sync = True
			item.item.save()

			self.set_sync_hash()

	def create_item(self, wc_product) -> None:
		"""Create an ERPNext Item from the given WooCommerce Product."""
		wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(wc_product.woocommerce_server))

		item = frappe.new_doc("Item")

		# Handle variants' attributes
		if wc_product.type in ["variable", "variation"]:
			self.create_or_update_item_attributes(wc_product)
			wc_attributes = json.loads(wc_product.attributes)
			# For variable products: only add variation-defining attributes as Item Attributes.
			# Non-variation attributes (Care, Fabric, Technique, etc.) are informational
			# in WooCommerce and should not become ERPNext Item Attributes.
			if wc_product.type == "variable":
				wc_attributes = [a for a in wc_attributes if a.get("variation", False)]
			for wc_attribute in wc_attributes:
				row = item.append("attributes")
				row.attribute = wc_attribute["name"]
				if wc_product.type == "variation":
					row.attribute_value = wc_attribute["option"]

		if wc_product.type == "variable":
			item.has_variants = 1

		if wc_product.type == "variation":
			woocommerce_product_name = generate_woocommerce_record_name_from_domain_and_id(
				wc_product.woocommerce_server, wc_product.parent_id
			)
			parent_item, _parent_wc_product = run_item_sync(woocommerce_product_name=woocommerce_product_name)
			item.variant_of = parent_item.item_code

		# Flexible item code naming (ported from connector)
		desired_item_code = (
			wc_product.sku
			if wc_server.name_by == "Product SKU" and wc_product.sku
			else str(wc_product.woocommerce_id)
		)

		# ── Pre-check: does an item with this code already exist? ──
		existing_item = frappe.db.get_value("Item", desired_item_code, "name")
		if existing_item:
			existing = frappe.get_doc("Item", existing_item)
			# Check whether the existing item is already linked to this WC product
			already_linked = any(
				str(iws.woocommerce_id) == str(wc_product.woocommerce_id)
				and iws.woocommerce_server in (wc_product.woocommerce_server, wc_server.name)
				for iws in existing.woocommerce_servers
			)
			if already_linked:
				# The item exists and is already linked — switch to the update path
				self.item = ERPNextItemToSync(
					item=existing,
					item_woocommerce_server_idx=next(
						iws.idx
						for iws in existing.woocommerce_servers
						if iws.woocommerce_server in (wc_product.woocommerce_server, wc_server.name)
					),
				)
				self.update_item(wc_product, self.item)
				return

			# The existing item is unrelated — use a server-qualified code to avoid collision
			desired_item_code = f"{wc_product.woocommerce_server}-{wc_product.woocommerce_id}"

		item.item_code = desired_item_code
		item.stock_uom = wc_server.uom or _("Nos")
		item.item_group = wc_server.item_group
		item.item_name = wc_product.woocommerce_name
		row = item.append("woocommerce_servers")
		row.woocommerce_id = wc_product.woocommerce_id
		row.woocommerce_server = wc_server.name
		item.flags.ignore_mandatory = True
		item.flags.created_by_sync = True

		if wc_server.enable_image_sync:
			wc_product_images = json.loads(wc_product.images)
			if len(wc_product_images) > 0:
				item.image = wc_product_images[0]["src"]

		_modified, item = self.set_item_fields(item=item)
		item.flags.created_by_sync = True

		# Register SKU as a scannable barcode on the item
		if wc_product.sku:
			row = item.append("barcodes")
			row.barcode = wc_product.sku
			row.barcode_type = ""

		# Store non-variation informational attributes (e.g. Care, Fabric, Technique)
		# in item description. These have variation=false in WooCommerce — they are
		# product info, not variant-defining, and can have long values unsuitable for
		# ERPNext Item Attribute abbr (30-char limit).
		if wc_product.type != "variation" and wc_product.attributes:
			wc_all_attrs = json.loads(wc_product.attributes)
			info_attrs = [a for a in wc_all_attrs if not a.get("variation", False)]
			if info_attrs:
				rows_html = "".join(
					f"<tr><td><strong>{a['name']}</strong></td>"
					f"<td>{', '.join(str(v) for v in (a.get('options') or [a.get('option', '')]))}</td></tr>"
					for a in info_attrs
				)
				attr_table = (
					"<div class='wc-info-attributes' style='margin-top:12px;'>"
					"<table class='table table-condensed table-bordered'>"
					f"<tbody>{rows_html}</tbody>"
					"</table></div>"
				)
				item.description = (item.description or "") + attr_table

		item.insert()


		self.item = ERPNextItemToSync(
			item=item,
			item_woocommerce_server_idx=next(
				iws.idx
				for iws in item.woocommerce_servers
				if iws.woocommerce_server in (wc_product.woocommerce_server, wc_server.name)
			),
		)
		self.set_sync_hash()

	def create_or_update_item_attributes(self, wc_product):
		"""Create or update Item Attributes — accumulate values, don't replace."""
		if not wc_product.attributes:
			return
		wc_attributes = json.loads(wc_product.attributes)

		# For variable products: only import variation-defining attributes (variation=true).
		# Non-variation attributes (e.g. Care, Technique, Fabric) are informational in
		# WooCommerce and must not be imported as ERPNext Item Attributes — their long
		# option values can exceed the 30-char abbr field limit and crash the sync.
		if wc_product.type == "variable":
			wc_attributes = [a for a in wc_attributes if a.get("variation", False)]

		for wc_attribute in wc_attributes:
			if frappe.db.exists("Item Attribute", wc_attribute["name"]):
				item_attribute = frappe.get_doc("Item Attribute", wc_attribute["name"])
			else:
				item_attribute = frappe.get_doc(
					{"doctype": "Item Attribute", "attribute_name": wc_attribute["name"]}
				)

			options = (
				wc_attribute["options"] if wc_product.type == "variable" else [wc_attribute["option"]]
			)

			# Accumulate new attribute values rather than replacing existing ones
			existing_values = {val.attribute_value for val in item_attribute.item_attribute_values}
			new_values = set(options) - existing_values
			if new_values or len(item_attribute.item_attribute_values) == 0:
				if len(item_attribute.item_attribute_values) == 0:
					# No existing values — add all
					for option in options:
						row = item_attribute.append("item_attribute_values")
						row.attribute_value = option
						row.abbr = _safe_abbr(option)  # max 30 chars
				else:
					# Accumulate new values only
					for option in new_values:
						row = item_attribute.append("item_attribute_values")
						row.attribute_value = option
						row.abbr = _safe_abbr(option)  # max 30 chars

			item_attribute.flags.ignore_mandatory = True
			if not item_attribute.name:
				item_attribute.insert()
			else:
				item_attribute.save()

	def set_item_fields(self, item: Item) -> tuple[bool, Item]:
		"""
		If there are Field Mappings on WooCommerce Server, synchronise their values
		from WooCommerce to ERPNext (using JSONPath).
		"""
		item_dirty = False
		if item and self.woocommerce_product:
			wc_server = frappe.get_cached_doc(
				"WooCommerce Server", resolve_wc_server_name(self.woocommerce_product.woocommerce_server)
			)
			if wc_server.item_field_map:
				woocommerce_product_dict = (
					self.woocommerce_product.deserialize_attributes_of_type_dict_or_list(
						self.woocommerce_product.to_dict()
					)
				)
				for field_map in wc_server.item_field_map:
					erpnext_item_field_name = field_map.erpnext_field_name.split(" | ")
					jsonpath_expr = parse(field_map.woocommerce_field_name)
					woocommerce_product_field_matches = jsonpath_expr.find(woocommerce_product_dict)
					if woocommerce_product_field_matches:
						setattr(item, erpnext_item_field_name[0], woocommerce_product_field_matches[0].value)
						item_dirty = True
		return item_dirty, item

	def set_product_fields(self, woocommerce_product, item: ERPNextItemToSync) -> tuple[bool, object]:
		"""
		If there are Field Mappings on WooCommerce Server, synchronise their values
		from ERPNext to WooCommerce (using JSONPath).
		Returns True if woocommerce_product was changed.
		"""
		wc_product_dirty = False
		if item and woocommerce_product:
			wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(woocommerce_product.woocommerce_server))
			if wc_server.item_field_map:
				wc_product_with_deserialised_fields = (
					woocommerce_product.deserialize_attributes_of_type_dict_or_list(woocommerce_product)
				)

				for field_map in wc_server.item_field_map:
					erpnext_item_field_name = field_map.erpnext_field_name.split(" | ")
					erpnext_item_field_value = getattr(item.item, erpnext_item_field_name[0])

					jsonpath_expr = parse(field_map.woocommerce_field_name)
					woocommerce_product_field_matches = jsonpath_expr.find(
						wc_product_with_deserialised_fields
					)

					if len(woocommerce_product_field_matches) == 0:
						if woocommerce_product.name:
							raise ValueError(
								_("Field <code>{0}</code> not found in WooCommerce Product {1}").format(
									field_map.woocommerce_field_name, woocommerce_product.name
								)
							)
						else:
							continue

					woocommerce_product_field_value = woocommerce_product_field_matches[0].value
					if erpnext_item_field_value != woocommerce_product_field_value:
						jsonpath_expr.update(wc_product_with_deserialised_fields, erpnext_item_field_value)
						wc_product_dirty = True

				if wc_product_dirty:
					woocommerce_product = woocommerce_product.serialize_attributes_of_type_dict_or_list(
						wc_product_with_deserialised_fields
					)

		return wc_product_dirty, woocommerce_product

	def set_sync_hash(self):
		"""
		Set the last sync hash using db.set_value (no ORM triggers, no modified timestamp update).
		"""
		frappe.db.set_value(
			"Item WooCommerce Server",
			self.item.item_woocommerce_server.name,
			"woocommerce_last_sync_hash",
			self.woocommerce_product.woocommerce_date_modified,
			update_modified=False,
		)

		# Auto-enable items that were synced (e.g. ordered on WooCommerce)
		frappe.db.set_value(
			"Item WooCommerce Server",
			self.item.item_woocommerce_server.name,
			"enabled",
			1,
			update_modified=False,
		)


# ────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────

def get_list_of_wc_products(
	item: ERPNextItemToSync | None = None, date_time_from: datetime | str | None = None
) -> list:
	"""
	Fetch WooCommerce Products, optionally filtered by date or linked Item.
	If neither parameter is provided, fetches ALL products.
	"""
	wc_records_per_page_limit = 100
	page_length = wc_records_per_page_limit
	new_results = True
	start = 0
	filters = []
	wc_products = []
	servers = None

	if date_time_from:
		filters.append(["WooCommerce Product", "date_modified", ">", date_time_from])
	if item:
		filters.append(["WooCommerce Product", "id", "=", item.item_woocommerce_server.woocommerce_id])
		resolved = resolve_wc_server_name(item.item_woocommerce_server.woocommerce_server)
		servers = [item.item_woocommerce_server.woocommerce_server, resolved]
		# Deduplicate
		servers = list(set(servers))

	while new_results:
		woocommerce_product = frappe.get_doc({"doctype": "WooCommerce Product"})
		new_results = woocommerce_product.get_list(
			args={
				"filters": filters,
				"page_length": page_length,
				"start": start,
				"servers": servers,
				"as_doc": True,
			}
		)
		for wc_product in new_results:
			wc_products.append(wc_product)
		start += page_length
		if len(new_results) < page_length:
			new_results = []

	return wc_products


def get_item_price_rate(item: ERPNextItemToSync):
	"""Get the Item Price if Item Price sync is enabled."""
	wc_server = frappe.get_cached_doc("WooCommerce Server", resolve_wc_server_name(item.item_woocommerce_server.woocommerce_server))
	if wc_server.enable_price_list_sync:
		item_prices = frappe.get_all(
			"Item Price",
			filters={"item_code": item.item.item_code, "price_list": wc_server.price_list},
			fields=["price_list_rate", "valid_upto"],
		)
		return next(
			(
				price.price_list_rate
				for price in item_prices
				if not price.valid_upto or price.valid_upto > now()
			),
			None,
		)


def clear_sync_hash_and_run_item_sync(item_code: str):
	"""Clear the last sync hash and trigger item sync."""
	iws = frappe.qb.DocType("Item WooCommerce Server")

	iwss = (
		frappe.qb.from_(iws)
		.where(iws.enabled == 1)
		.where(iws.parent == item_code)
		.select(iws.name)
	).run(as_dict=True)

	for iws_row in iwss:
		frappe.db.set_value(
			"Item WooCommerce Server",
			iws_row.name,
			"woocommerce_last_sync_hash",
			None,
			update_modified=False,
		)

	if len(iwss) > 0:
		run_item_sync(item_code=item_code, enqueue=True)
