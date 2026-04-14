"""
WooCommerce Center — tasks/sync.py
Base class for all WooCommerce synchronisation tasks.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Ported and extended from woocommerce_fusion (Starktail).
"""

import frappe
from frappe import _dict


class SynchroniseWooCommerce:
	"""
	Base class for managing synchronisation of WooCommerce data with ERPNext data.
	Provides multi-server iteration support.
	"""

	servers: list

	def __init__(self, servers: list | None = None) -> None:
		self.servers = servers if servers else self.get_wc_servers()

	@staticmethod
	def get_wc_servers():
		"""Fetch all enabled WooCommerce Server documents."""
		wc_servers = frappe.get_all("WooCommerce Server", filters={"enable_sync": 1})
		return [frappe.get_doc("WooCommerce Server", server.name) for server in wc_servers]
