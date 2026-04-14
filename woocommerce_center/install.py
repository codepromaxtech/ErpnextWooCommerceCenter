"""
WooCommerce Center — install.py
Handles after_install and after_uninstall lifecycle hooks.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
"""

import frappe
from click import echo
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


# ──────────────────────────────────────────
# Custom Fields Definition
# ──────────────────────────────────────────
CUSTOM_FIELDS = {
	"Customer": [
		{
			"fieldname": "woocommerce_tab",
			"label": "WooCommerce",
			"fieldtype": "Tab Break",
			"insert_after": "sales_team_section",
		},
		{
			"fieldname": "woocommerce_server",
			"label": "WooCommerce Server",
			"fieldtype": "Link",
			"options": "WooCommerce Server",
			"insert_after": "woocommerce_tab",
			"read_only": 1,
		},
		{
			"fieldname": "woocommerce_identifier",
			"label": "WooCommerce Identifier",
			"fieldtype": "Data",
			"insert_after": "woocommerce_server",
			"read_only": 1,
			"description": "Email or Guest-{order_id} used to uniquely identify this customer in WooCommerce",
		},
		{
			"fieldname": "woocommerce_is_guest",
			"label": "Is WooCommerce Guest",
			"fieldtype": "Check",
			"insert_after": "woocommerce_identifier",
			"read_only": 1,
		},
	],
	"Address": [
		{
			"fieldname": "woocommerce_identifier",
			"label": "WooCommerce Identifier",
			"fieldtype": "Data",
			"insert_after": "disabled",
			"read_only": 1,
		},
	],
	"Contact": [
		{
			"fieldname": "woocommerce_identifier",
			"label": "WooCommerce Identifier",
			"fieldtype": "Data",
			"insert_after": "company_name",
			"read_only": 1,
		},
	],
	"Sales Order": [
		{
			"fieldname": "custom_woocommerce_tab",
			"label": "WooCommerce",
			"fieldtype": "Tab Break",
			"insert_after": "terms",
		},
		{
			"fieldname": "woocommerce_id",
			"label": "WooCommerce Order ID",
			"fieldtype": "Data",
			"insert_after": "custom_woocommerce_tab",
			"read_only": 1,
			"in_list_view": 1,
		},
		{
			"fieldname": "woocommerce_server",
			"label": "WooCommerce Server",
			"fieldtype": "Link",
			"options": "WooCommerce Server",
			"insert_after": "woocommerce_id",
			"read_only": 1,
		},
		{
			"fieldname": "woocommerce_status",
			"label": "WooCommerce Status",
			"fieldtype": "Data",
			"insert_after": "woocommerce_server",
			"read_only": 1,
		},
		{
			"fieldname": "woocommerce_payment_method",
			"label": "WooCommerce Payment Method",
			"fieldtype": "Data",
			"insert_after": "woocommerce_status",
			"read_only": 1,
		},
		{
			"fieldname": "woocommerce_payment_entry",
			"label": "WooCommerce Payment Entry",
			"fieldtype": "Link",
			"options": "Payment Entry",
			"insert_after": "woocommerce_payment_method",
			"read_only": 1,
		},
		{
			"fieldname": "woocommerce_shipment_tracking_html",
			"label": "Shipment Tracking",
			"fieldtype": "HTML",
			"insert_after": "woocommerce_payment_entry",
		},
		{
			"fieldname": "custom_woocommerce_last_sync_hash",
			"label": "Last WooCommerce Sync Hash",
			"fieldtype": "Data",
			"insert_after": "woocommerce_shipment_tracking_html",
			"read_only": 1,
			"hidden": 1,
		},
		{
			"fieldname": "custom_woocommerce_customer_note",
			"label": "Customer Note (WooCommerce)",
			"fieldtype": "Text",
			"insert_after": "custom_woocommerce_last_sync_hash",
			"read_only": 1,
		},
		{
			"fieldname": "custom_attempted_woocommerce_auto_payment_entry",
			"label": "Attempted WooCommerce Auto Payment Entry",
			"fieldtype": "Check",
			"insert_after": "custom_woocommerce_customer_note",
			"read_only": 1,
			"hidden": 1,
		},
	],
	"Item": [
		{
			"fieldname": "custom_woocommerce_tab",
			"label": "WooCommerce",
			"fieldtype": "Tab Break",
			"insert_after": "website_section",
		},
		{
			"fieldname": "woocommerce_servers",
			"label": "WooCommerce Servers",
			"fieldtype": "Table",
			"options": "Item WooCommerce Server",
			"insert_after": "custom_woocommerce_tab",
		},
	],
}


# ──────────────────────────────────────────
# After Install
# ──────────────────────────────────────────
def after_install():
	echo("WooCommerce Center: Checking for conflicting apps...")
	check_for_conflicting_apps()

	echo("WooCommerce Center: Creating custom fields...")
	make_custom_fields()

	echo("WooCommerce Center: Creating required records...")
	make_woocommerce_records()

	echo("WooCommerce Center: Installation complete ✓")


# ──────────────────────────────────────────
# After Uninstall
# ──────────────────────────────────────────
def after_uninstall():
	echo("WooCommerce Center: Removing custom fields...")
	delete_custom_fields()
	echo("WooCommerce Center: Uninstall complete ✓")


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────
def check_for_conflicting_apps():
	"""Warn if older competing WooCommerce apps are installed."""
	conflicting = [
		"woocommerce_fusion",
		"woocommerceconnector",
		"woocommerce_integration",
	]
	try:
		installed = frappe.get_installed_apps()
		found = [a for a in conflicting if a in installed]
		if found:
			frappe.msgprint(
				f"⚠️  Warning: The following WooCommerce apps are still installed and may conflict "
				f"with WooCommerce Center: <b>{', '.join(found)}</b>. "
				"It is strongly recommended to uninstall them before using WooCommerce Center.",
				title="Conflicting Apps Detected",
				indicator="orange",
			)
	except Exception:
		pass  # Non-fatal — just a warning


def make_custom_fields():
	"""Create all custom fields required by WooCommerce Center."""
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def delete_custom_fields():
	"""Remove all custom fields created by WooCommerce Center."""
	for doctype, fields in CUSTOM_FIELDS.items():
		fieldnames = [f["fieldname"] for f in fields]
		frappe.db.delete(
			"Custom Field",
			{"fieldname": ("in", fieldnames), "dt": doctype},
		)
		frappe.clear_cache(doctype=doctype)


def make_woocommerce_records():
	"""Ensure prerequisite records exist."""
	# Item Groups
	groups = [("All Item Groups", None), ("WooCommerce Products", "All Item Groups")]
	for group_name, parent in groups:
		if not frappe.db.exists("Item Group", group_name):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": group_name,
					"parent_item_group": parent,
					"is_group": 1 if parent is None else 0,
				}
			).insert(ignore_permissions=True)

	# Default weight UOMs
	weight_uoms = ["g", "kg", "lb", "lbs", "oz"]
	for uom in weight_uoms:
		if not frappe.db.exists("UOM", uom):
			try:
				frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
			except Exception:
				pass  # May already exist

	frappe.db.commit()
