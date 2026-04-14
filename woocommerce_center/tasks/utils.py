"""
WooCommerce Center — tasks/utils.py
APIWithRequestLogging: wraps the woocommerce.API to log every HTTP request/response.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Ported and extended from woocommerce_fusion (Starktail).
"""

import frappe
from woocommerce import API


class APIWithRequestLogging(API):
	"""
	A WooCommerce API wrapper that logs every HTTP request and response
	to the 'WooCommerce Request Log' doctype for debugging and audit purposes.
	"""

	def _request(self, method, endpoint, data=None, params=None, **kwargs):
		"""Override _request to log before and after each API call."""
		response = super()._request(method, endpoint, data=data, params=params, **kwargs)
		self._log_request(method=method, endpoint=endpoint, data=data, params=params, response=response)
		return response

	def _log_request(self, method: str, endpoint: str, data, params, response):
		"""Persist the HTTP request/response to WooCommerce Request Log."""
		try:
			log = frappe.new_doc("WooCommerce Request Log")
			log.request_method = method.upper()
			log.endpoint = endpoint
			log.request_url = response.request.url if response and response.request else None
			log.request_body = (
				frappe.as_json(data, indent=2) if isinstance(data, (dict, list)) else str(data or "")
			)
			log.request_params = frappe.as_json(params, indent=2) if params else ""
			log.response_status_code = response.status_code if response else None
			log.response_body = (
				response.text[:10000] if response and response.text else ""
			)  # Truncate large responses
			log.insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			# Never let logging failure break the actual sync
			pass
