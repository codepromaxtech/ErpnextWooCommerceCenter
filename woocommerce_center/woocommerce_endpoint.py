"""
WooCommerce Center — woocommerce_endpoint.py
Real-time webhook receiver from WooCommerce.
Supports: order.created, order.updated, order.deleted, product.updated

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

	if not incoming_sig:
		frappe.log_error(
			"WooCommerce Webhook Debug",
			f"No X-Wc-Webhook-Signature header found.\n"
			f"Headers: {dict(frappe.request.headers)}\n"
			f"Enabled servers: {[s.name for s in servers]}",
		)
		return None

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


def _is_wc_ping() -> bool:
	"""
	Detect WooCommerce webhook verification "ping" requests.
	WooCommerce sends these when a webhook is first created to verify the URL is reachable.
	Ping characteristics:
	  - X-Wc-Webhook-Topic header may be empty, 'action.woocommerce_webhook_deliver_ping',
	    or contain the actual topic
	  - X-Wc-Webhook-Resource is 'action'
	  - The body may be empty or contain just the webhook_id
	"""
	topic = frappe.get_request_header("X-Wc-Webhook-Topic", "")
	resource = frappe.get_request_header("X-Wc-Webhook-Resource", "")

	# WooCommerce ping topic
	if "ping" in topic.lower():
		return True

	# Resource = "action" is used for pings
	if resource == "action":
		return True

	# HEAD/GET are also pings
	if frappe.request.method in ("GET", "HEAD"):
		return True

	return False


def verify_webhook() -> object:
	"""
	Verify the HMAC-SHA256 signature of an incoming WooCommerce webhook.
	Returns the matching WooCommerce Server document.
	Raises on failure.
	"""
	if not frappe.request.data:
		frappe.log_error("WooCommerce Webhook Error", "No webhook payload received")
		frappe.throw(_("No webhook data"), exc=frappe.ValidationError)

	server = _get_server_for_webhook()
	if not server:
		# Enhanced debug logging
		incoming_sig = frappe.get_request_header("X-Wc-Webhook-Signature", "(missing)")
		topic = frappe.get_request_header("X-Wc-Webhook-Topic", "(missing)")
		source = frappe.get_request_header("X-Wc-Webhook-Source", "(missing)")
		payload_preview = frappe.request.data[:200] if frappe.request.data else b"(empty)"
		frappe.log_error(
			"WooCommerce Webhook Error",
			f"Webhook signature verification failed — no matching server.\n\n"
			f"Topic: {topic}\n"
			f"Source: {source}\n"
			f"Signature: {incoming_sig}\n"
			f"Payload (first 200 bytes): {payload_preview}\n\n"
			f"Ensure the webhook secret in WooCommerce matches the 'Webhook Secret' "
			f"field in your WooCommerce Server document in ERPNext.",
		)
		frappe.throw(_("Webhook verification failed"), exc=frappe.AuthenticationError)

	frappe.set_user("Administrator")
	return server


def process_request_data() -> tuple[bool, Optional[dict]]:
	"""
	Parse and return the webhook payload.
	Returns (skip, data) — skip=True means the payload is a WooCommerce test ping.
	"""
	raw = frappe.request.data
	if isinstance(raw, (bytes, bytearray)):
		raw = raw.decode("utf-8")

	if not raw:
		return True, None

	# WooCommerce sends a test ping with webhook_id in query string
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


def _prepare_webhook_request():
	"""
	Common setup for all webhook handler endpoints.
	Disables Frappe CSRF protection (external POST from WooCommerce has no CSRF token).
	Returns "ok" for ping requests, None otherwise.
	"""
	# Critical: bypass CSRF for external webhook POST requests
	frappe.flags.ignore_csrf = True

	# Handle ping/verification requests before HMAC check
	if _is_wc_ping():
		return "ok"

	return None


# ──────────────────────────────────────────
# Webhook Handlers
# ──────────────────────────────────────────

@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def create_order():
	"""Webhook: order.created"""
	ping_response = _prepare_webhook_request()
	if ping_response:
		return ping_response

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


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def update_order():
	"""Webhook: order.updated"""
	ping_response = _prepare_webhook_request()
	if ping_response:
		return ping_response

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


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def delete_order():
	"""Webhook: order.deleted"""
	ping_response = _prepare_webhook_request()
	if ping_response:
		return ping_response

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


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def update_product():
	"""Webhook: product.updated"""
	ping_response = _prepare_webhook_request()
	if ping_response:
		return ping_response

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
