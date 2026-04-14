"""
WooCommerce Center — utils.py
Shared utility functions.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
"""

import frappe
from erpnext.setup.utils import _enable_all_roles_for_admin, set_defaults_for_tests
from frappe.utils.data import now_datetime


def before_tests():
	"""Set up test environment for WooCommerce Center tests."""
	frappe.clear_cache()

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	if not frappe.db.a_row_exists("Company"):
		current_year = now_datetime().year
		setup_complete(
			{
				"currency": "BDT",
				"full_name": "Test User",
				"company_name": "CodeProMax Tech (Test)",
				"timezone": "Asia/Dhaka",
				"company_abbr": "CPT",
				"industry": "Technology",
				"country": "Bangladesh",
				"fy_start_date": f"{current_year}-01-01",
				"fy_end_date": f"{current_year}-12-31",
				"language": "english",
				"company_tagline": "Testing WooCommerce Center",
				"email": "test@codepromaxtech.com",
				"password": "test",
				"chart_of_accounts": "Standard",
			}
		)

	_enable_all_roles_for_admin()
	set_defaults_for_tests()
	create_test_currency_exchange()
	frappe.db.commit()  # nosemgrep


def create_test_currency_exchange():
	"""Create Currency Exchange records used in tests."""
	currencies = ["USD", "EUR", "GBP"]
	for currency in currencies:
		cur_exchange = frappe.new_doc("Currency Exchange")
		cur_exchange.date = "2024-01-01"
		cur_exchange.from_currency = currency
		cur_exchange.to_currency = "BDT"
		cur_exchange.for_buying = 1
		cur_exchange.for_selling = 1
		cur_exchange.exchange_rate = 110.0
		cur_exchange.insert(ignore_if_duplicate=True)


def get_weight_in_woocommerce_unit(weight: float, source_uom: str, target_uom: str) -> float:
	"""
	Convert a weight value from source_uom to target_uom.
	Supports: g, kg, lb, lbs, oz
	Ported and improved from ErpnextWooCommerceConnector (libracore).
	"""
	# Convert everything to grams first
	to_grams = {
		"g": 1.0,
		"kg": 1000.0,
		"lb": 453.592,
		"lbs": 453.592,
		"oz": 28.3495,
	}
	# Then convert from grams to target
	from_grams = {
		"g": 1.0,
		"kg": 0.001,
		"lb": 0.00220462,
		"lbs": 0.00220462,
		"oz": 0.035274,
	}
	src = source_uom.lower()
	tgt = target_uom.lower()
	if src not in to_grams or tgt not in from_grams:
		return weight  # fallback: return as-is
	weight_in_grams = weight * to_grams[src]
	return weight_in_grams * from_grams[tgt]


def get_country_name_from_code(country_code: str) -> str | None:
	"""Return the ERPNext country name for a 2-letter ISO country code."""
	if not country_code:
		return None
	return frappe.db.get_value("Country", {"code": country_code.lower()}, "name")


def get_uom(sku: str | None, default_uom: str = "Nos") -> str:
	"""
	Return an ERPNext UOM — auto-create from SKU if it doesn't exist.
	Ported from woocommerce_integration (ALYF).
	"""
	if sku:
		if not frappe.db.exists("UOM", sku):
			try:
				frappe.get_doc({"doctype": "UOM", "uom_name": sku}).insert(ignore_permissions=True)
			except Exception:
				return default_uom or "Nos"
		return sku
	return default_uom or "Nos"


def add_tax_details(document, price: float, description: str, account_head: str) -> None:
	"""
	Append a tax/charge row to the given document's taxes table.
	Ported from woocommerce_integration (ALYF) with null-guard.
	"""
	if not price or not account_head:
		return
	document.append(
		"taxes",
		{
			"charge_type": "Actual",
			"account_head": account_head,
			"tax_amount": price,
			"description": description,
		},
	)
