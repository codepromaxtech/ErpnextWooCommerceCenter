"""
WooCommerce Center — Custom Exceptions
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
"""


class WooCommerceCenterError(Exception):
	"""Base exception for WooCommerce Center."""
	pass


class SyncDisabledError(WooCommerceCenterError):
	"""Raised when sync is disabled for a WooCommerce Server."""

	def __init__(self, wc_server=None):
		self.wc_server = wc_server
		msg = (
			f"Sync is disabled for WooCommerce Server '{wc_server.name}'"
			if wc_server
			else "Sync is disabled"
		)
		super().__init__(msg)


class WooCommerceOrderNotFoundError(WooCommerceCenterError):
	"""Raised when the linked WooCommerce Order cannot be found (e.g. deleted)."""

	def __init__(self, sales_order=None):
		self.sales_order = sales_order
		msg = (
			f"WooCommerce Order linked to Sales Order '{sales_order.name}' could not be found"
			if sales_order
			else "WooCommerce Order not found"
		)
		super().__init__(msg)


class WooCommerceAPIError(WooCommerceCenterError):
	"""Raised when the WooCommerce REST API returns an unexpected response."""

	def __init__(self, message="WooCommerce API error", status_code=None, response_text=None):
		self.status_code = status_code
		self.response_text = response_text
		super().__init__(message)


class WebhookVerificationError(WooCommerceCenterError):
	"""Raised when a WooCommerce webhook signature cannot be verified."""
	pass
