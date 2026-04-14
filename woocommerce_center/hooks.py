"""
WooCommerce Center — hooks.py
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
ERPNext v15 / v16 compatible
"""

from . import __version__ as app_version  # noqa: F401

app_name = "woocommerce_center"
app_title = "WooCommerce Center"
app_publisher = "CodeProMax Tech"
app_description = "All-in-one WooCommerce ↔ ERPNext connector — orders, products, stock, prices, payments, webhooks, multi-site"
app_email = "codepromaxtech@gmail.com"
app_license = "MIT"
app_icon = "/assets/woocommerce_center/images/woocommerce_center_logo.svg"
app_logo_url = "/assets/woocommerce_center/images/woocommerce_center_logo.svg"
app_color = "#7f54b3"  # WooCommerce purple

# ──────────────────────────────────────────
# Install / Uninstall
# ──────────────────────────────────────────
after_install = "woocommerce_center.install.after_install"
after_uninstall = "woocommerce_center.install.after_uninstall"

# ──────────────────────────────────────────
# Testing
# ──────────────────────────────────────────
before_tests = "woocommerce_center.utils.before_tests"

# ──────────────────────────────────────────
# Desk JS Includes
# ──────────────────────────────────────────
doctype_js = {
	"Sales Order": "public/js/selling/sales_order.js",
	"Item": "public/js/stock/item.js",
}
doctype_list_js = {
	"Sales Order": "public/js/selling/sales_order_list.js",
}

# ──────────────────────────────────────────
# DocType Class Overrides
# ──────────────────────────────────────────
override_doctype_class = {
	"Sales Order": "woocommerce_center.overrides.selling.sales_order.CustomSalesOrder",
}

# ──────────────────────────────────────────
# Document Events
# ──────────────────────────────────────────
doc_events = {
	# Stock-level sync triggers
	"Stock Entry": {
		"on_submit": "woocommerce_center.tasks.stock_update.update_stock_levels_for_woocommerce_item",
		"on_cancel": "woocommerce_center.tasks.stock_update.update_stock_levels_for_woocommerce_item",
	},
	"Stock Reconciliation": {
		"on_submit": "woocommerce_center.tasks.stock_update.update_stock_levels_for_woocommerce_item",
		"on_cancel": "woocommerce_center.tasks.stock_update.update_stock_levels_for_woocommerce_item",
	},
	"Sales Invoice": {
		"on_submit": "woocommerce_center.tasks.stock_update.update_stock_levels_for_woocommerce_item",
		"on_cancel": "woocommerce_center.tasks.stock_update.update_stock_levels_for_woocommerce_item",
	},
	"Delivery Note": {
		"on_submit": "woocommerce_center.tasks.stock_update.update_stock_levels_for_woocommerce_item",
		"on_cancel": "woocommerce_center.tasks.stock_update.update_stock_levels_for_woocommerce_item",
	},
	# Price sync trigger
	"Item Price": {
		"on_update": "woocommerce_center.tasks.sync_item_prices.update_item_price_for_woocommerce_item_from_hook",
	},
	# Sales Order status sync (ERPNext → WooCommerce)
	"Sales Order": {
		"on_submit": "woocommerce_center.tasks.sync_sales_orders.run_sales_order_sync_from_hook",
	},
	# Item sync trigger (ERPNext → WooCommerce)
	"Item": {
		"on_update": "woocommerce_center.tasks.sync_items.run_item_sync_from_hook",
		"after_insert": "woocommerce_center.tasks.sync_items.run_item_sync_from_hook",
	},
}

# ──────────────────────────────────────────
# Scheduled Tasks
# ──────────────────────────────────────────
scheduler_events = {
	"hourly_long": [
		"woocommerce_center.tasks.sync_sales_orders.sync_woocommerce_orders_modified_since",
		"woocommerce_center.tasks.sync_items.sync_woocommerce_products_modified_since",
	],
	"daily_long": [
		"woocommerce_center.tasks.stock_update.update_stock_levels_for_all_enabled_items_in_background",
		"woocommerce_center.tasks.sync_item_prices.run_item_price_sync_in_background",
	],
}

# ──────────────────────────────────────────
# Fixtures — Custom Fields exported/imported with the app
# ──────────────────────────────────────────
fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				(
					# Customer fields
					"Customer-woocommerce_server",
					"Customer-woocommerce_identifier",
					"Customer-woocommerce_is_guest",
					# Address fields
					"Address-woocommerce_identifier",
					# Contact fields
					"Contact-woocommerce_identifier",
					# Sales Order fields
					"Sales Order-woocommerce_id",
					"Sales Order-woocommerce_server",
					"Sales Order-woocommerce_status",
					"Sales Order-woocommerce_payment_method",
					"Sales Order-woocommerce_shipment_tracking_html",
					"Sales Order-woocommerce_payment_entry",
					"Sales Order-custom_attempted_woocommerce_auto_payment_entry",
					"Sales Order-custom_woocommerce_last_sync_hash",
					"Sales Order-custom_woocommerce_customer_note",
					# Item fields
					"Item-woocommerce_servers",
					"Item-custom_woocommerce_tab",
				),
			]
		],
	}
]

# ──────────────────────────────────────────
# Log Clearing
# ──────────────────────────────────────────
default_log_clearing_doctypes = {
	"WooCommerce Request Log": 7,  # Auto-clear logs older than 7 days
}

# ──────────────────────────────────────────
# Ignore cascade deletes for log doctype
# ──────────────────────────────────────────
ignore_links_on_delete = ["WooCommerce Request Log"]

# ──────────────────────────────────────────
# Help / Documentation
# ──────────────────────────────────────────
standard_help_items = [
	{
		"item_label": "WooCommerce Center Documentation",
		"item_type": "Route",
		"route": "/woocommerce_center_docs",
		"is_standard": 1,
	},
]
