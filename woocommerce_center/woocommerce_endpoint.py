"""
WooCommerce Center — woocommerce_endpoint.py
Real-time webhook receiver from WooCommerce.
Supports: order.created, order.updated, order.deleted

Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
"""

import base64
import hashlib
import json
from hmac import new as HMAC
from typing import Optional

import frappe
from frappe import _

from woocommerce_center.exceptions import WebhookVerificationError


def _get_server_for_webhook() -> Optional[object]:
	"""
	Find the WooCommerce Server whose webhook_secret matches the incoming request.
	Tries each enabled server until one validates.
	"""
	servers = frappe.get_all(
		"WooCommerce Server",
		filters={"enable_sync": 1},
		fields=["name"],
	)
	incoming_sig = frappe.get_request_header("X-Wc-Webhook-Signature", "")
	payload = frappe.request.data

	for server in servers:
		server_doc = frappe.get_doc("WooCommerce Server", server.name)
		webhook_secret = server_doc.get_password("webhook_secret", raise_exception=False)
		if not webhook_secret:
			continue
		expected_sig = base64.b64encode(
			HMAC(
				webhook_secret.encode("utf8"),
				payload,
				hashlib.sha256,
			).digest()
		).decode("utf8")
		if incoming_sig == expected_sig:
			return server_doc
	return None


def verify_webhook() -> object:
	"""
	Verify the HMAC-SHA256 signature of an incoming WooCommerce webhook.
	Returns the matching WooCommerce Server document.
	Raises WebhookVerificationError if no server matches.
	Ported & enhanced from woocommerce_integration (ALYF).
	"""
	if not frappe.request.data:
		frappe.log_error("WooCommerce Webhook Error", "No webhook payload received")
		frappe.throw(_("No webhook data"), exc=frappe.ValidationError)

	server = _get_server_for_webhook()
	if not server:
		frappe.log_error("WooCommerce Webhook Error", "Webhook signature verification failed — no matching server found")
		frappe.throw(_("Webhook verification failed"), exc=frappe.AuthenticationError)

	# Set the frappe user to the server owner / system user so subsequent operations run with correct permissions
	frappe.set_user("Administrator")
	return server


def process_request_data() -> tuple[bool, Optional[dict]]:
	"""
	Parse and return the webhook payload.
	Returns (skip, data) — skip=True means the payload is a WooCommerce test ping.
	Ported from woocommerce_integration (ALYF).
	"""
	raw = frappe.request.data
	if isinstance(raw, (bytes, bytearray)):
		raw = raw.decode("utf-8")

	if not raw:
		return True, None

	# WooCommerce sends a test ping with webhook_id in query string (not the body)
	if isinstance(raw, str) and "webhook_id" in frappe.request.args:
		return True, None

	try:
		data = json.loads(raw)
		return False, data
	except json.JSONDecodeError:
		frappe.log_error("WooCommerce Webhook Error", f"Could not parse webhook payload: {raw[:500]}")
		return True, None


def _log_webhook_error(order_data: Optional[dict] = None):
	"""Log a webhook processing error."""
	log_payload = (
		frappe.as_json(order_data, indent=2)
		if isinstance(order_data, (dict, list))
		else str(order_data or "No payload")
	)
	error_message = frappe.get_traceback() + "\n\nWebhook Payload:\n" + log_payload
	frappe.log_error("WooCommerce Webhook Error", error_message)


# ──────────────────────────────────────────
# Webhook Handlers
# ──────────────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["POST"])
def create_order():
	"""
	Webhook: order.created
	Creates a new ERPNext Sales Order from the incoming WooCommerce order.
	Real-time — triggers immediately on new WooCommerce order.
	"""
	try:
		server = verify_webhook()
		skip, order_data = process_request_data()
		if skip:
			return "success"

		frappe.enqueue(
			"woocommerce_center.tasks.sync_sales_orders.run_sales_order_sync_from_webhook",
			queue="long",
			order_data=order_data,
			woocommerce_server_name=server.name,
		)
		return "queued"
	except (frappe.ValidationError, frappe.AuthenticationError):
		raise
	except Exception:
		_log_webhook_error()
		raise


@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_order():
	"""
	Webhook: order.updated
	Triggers a bidirectional sync for the updated WooCommerce order.
	"""
	try:
		server = verify_webhook()
		skip, order_data = process_request_data()
		if skip:
			return "success"

		frappe.enqueue(
			"woocommerce_center.tasks.sync_sales_orders.run_sales_order_sync_from_webhook",
			queue="long",
			order_data=order_data,
			woocommerce_server_name=server.name,
		)
		return "queued"
	except (frappe.ValidationError, frappe.AuthenticationError):
		raise
	except Exception:
		_log_webhook_error()
		raise


@frappe.whitelist(allow_guest=True, methods=["POST"])
def delete_order():
	"""
	Webhook: order.deleted / order.restored
	Cancels (or restores) the corresponding ERPNext Sales Order.
	"""
	try:
		server = verify_webhook()
		skip, order_data = process_request_data()
		if skip:
			return "success"

		woocommerce_id = order_data.get("id") if order_data else None
		if not woocommerce_id:
			return "no_id"

		frappe.enqueue(
			"woocommerce_center.tasks.sync_sales_orders.cancel_sales_order_from_webhook",
			queue="long",
			woocommerce_id=woocommerce_id,
			woocommerce_server_name=server.name,
		)
		return "queued"
	except (frappe.ValidationError, frappe.AuthenticationError):
		raise
	except Exception:
		_log_webhook_error()
		raise


@frappe.whitelist(allow_guest=True, methods=["POST"])
def update_product():
	"""
	Webhook: product.updated
	Triggers item sync for the updated WooCommerce product.
	"""
	try:
		server = verify_webhook()
		skip, product_data = process_request_data()
		if skip:
			return "success"

		frappe.enqueue(
			"woocommerce_center.tasks.sync_items.run_item_sync_from_webhook",
			queue="long",
			product_data=product_data,
			woocommerce_server_name=server.name,
		)
		return "queued"
	except (frappe.ValidationError, frappe.AuthenticationError):
		raise
	except Exception:
		_log_webhook_error()
		raise
