"""
WooCommerce Center — woocommerce/woocommerce_api.py
WooCommerceResource: Virtual Frappe Document that proxies all CRUD to the WooCommerce REST API.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Architecture ported and extended from woocommerce_fusion (Starktail).
"""

import json
from dataclasses import dataclass
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import format_datetime, get_datetime
from typing_extensions import Self

from woocommerce_center.exceptions import SyncDisabledError
from woocommerce_center.tasks.utils import APIWithRequestLogging

# Delimiter used to encode "server_domain~record_id" as a Frappe document name
WC_RESOURCE_DELIMITER = "~"


if frappe._dev_server:
	import urllib3
	urllib3.disable_warnings()


# ──────────────────────────────────────────
# Dataclass — one per WooCommerce Server
# ──────────────────────────────────────────
@dataclass
class WooCommerceAPI:
	"""Holds a live API connection to one WooCommerce Server."""
	api: APIWithRequestLogging
	woocommerce_server_url: str
	woocommerce_server: str  # Name of the WooCommerce Server doctype record


# ──────────────────────────────────────────
# Virtual Document Base Class
# ──────────────────────────────────────────
class WooCommerceResource(Document):
	"""
	Base class for virtual Frappe Documents that represent WooCommerce REST resources.
	Subclasses must set: resource (str), and optionally child_resource (str), field_setter_map (dict).

	All Frappe CRUD methods (load_from_db, db_insert, db_update) are proxied to the WooCommerce REST API.
	List views, count, and stats also hit the API directly.

	Multi-server support: _init_api() reads ALL enabled WooCommerce Servers and returns one API per server.
	"""

	wc_api_list: list[WooCommerceAPI] | None = None
	current_wc_api: WooCommerceAPI | None = None

	resource: str | None = None          # e.g. "orders", "products"
	child_resource: str | None = None    # e.g. "variations" (for product variants)
	field_setter_map: dict = None        # Maps Frappe field names → WooCommerce field names

	# ── API Initialisation ──────────────────
	@staticmethod
	def _init_api() -> list[WooCommerceAPI]:
		"""Initialise one API connection per enabled WooCommerce Server."""
		wc_servers = frappe.get_all("WooCommerce Server", fields=["name"])
		wc_servers = [frappe.get_doc("WooCommerce Server", s.name) for s in wc_servers]

		wc_api_list = []
		for server in wc_servers:
			if server.enable_sync != 1:
				continue
			url = server.woocommerce_server_url or ""
			if url and not url.startswith(("http://", "https://")):
				url = "https://" + url
			wc_api_list.append(
				WooCommerceAPI(
					api=APIWithRequestLogging(
						url=url,
						consumer_key=server.api_consumer_key,
						consumer_secret=server.get_password("api_consumer_secret"),
						version="wc/v3",
						timeout=40,
						verify_ssl=bool(server.verify_ssl),
					),
					woocommerce_server_url=url,
					woocommerce_server=server.name,
				)
			)

		if not wc_api_list:
			frappe.throw(_("At least one WooCommerce Server must be enabled"), SyncDisabledError)

		return wc_api_list

	def init_api(self):
		self.wc_api_list = self._init_api()

	# ── Dict-like access (for jsonpath-ng) ──
	def __getitem__(self, key):
		return self.get(key)

	def __setitem__(self, key, value):
		self.set(key, value)

	def __contains__(self, key):
		fields = [f.fieldname for f in self.meta.fields]
		fields.append("name")
		return key in fields

	# ── Single Record Load ───────────────────
	def load_from_db(self):
		"""Fetch a single WooCommerce record (used in Form view)."""
		if not self.wc_api_list:
			self.init_api()

		wc_server_domain, record_id = get_domain_and_id_from_woocommerce_record_name(self.name)

		self.current_wc_api = next(
			(api for api in self.wc_api_list if wc_server_domain in api.woocommerce_server_url),
			None,
		)
		if not self.current_wc_api:
			log_and_raise_error(error_text=f"No API found for domain '{wc_server_domain}'")

		record = None

		# Try loading as a top-level resource first
		try:
			response = self.current_wc_api.api.get(f"{self.resource}/{record_id}")
			if response.status_code == 200:
				record = response.json()
		except Exception:
			pass

		# If top-level load failed or returned a variation with parent_id,
		# and this resource supports child_resource, try loading as a child
		if record and record.get("parent_id") and getattr(self, "child_resource", None):
			parent_id = record["parent_id"]
			try:
				child_response = self.current_wc_api.api.get(
					f"{self.resource}/{parent_id}/{self.child_resource}/{record_id}"
				)
				if child_response.status_code == 200:
					record = child_response.json()
					record["parent_id"] = parent_id
			except Exception:
				pass  # Keep the top-level record if child endpoint fails

		# If top-level load failed entirely, try as a child resource
		# by looking up parent_id from ERPNext Item
		if not record or "id" not in record:
			parent_id = self._get_parent_id_from_erpnext(wc_server_domain, record_id)
			if parent_id and getattr(self, "child_resource", None):
				try:
					child_response = self.current_wc_api.api.get(
						f"{self.resource}/{parent_id}/{self.child_resource}/{record_id}"
					)
					if child_response.status_code == 200:
						record = child_response.json()
						record["parent_id"] = parent_id
				except Exception:
					pass

		if not record or "id" not in record:
			log_and_raise_error(
				error_text=f"load_from_db failed — no 'id' in response for {self.resource} #{record_id}:\n{record}"
			)

		record = self.pre_init_document(record, woocommerce_server_url=self.current_wc_api.woocommerce_server_url)
		record = self.after_load_from_db(record)
		self.call_super_init(record)

	def _get_parent_id_from_erpnext(self, wc_server_domain, record_id):
		"""Look up the parent WooCommerce product ID from ERPNext for a variation."""
		try:
			iws = frappe.qb.DocType("Item WooCommerce Server")
			itm = frappe.qb.DocType("Item")

			# Find the ERPNext Item for this WC product ID
			item_data = (
				frappe.qb.from_(iws)
				.join(itm).on(iws.parent == itm.name)
				.where(iws.woocommerce_id == str(record_id))
				.where(iws.woocommerce_server == wc_server_domain)
				.select(itm.variant_of)
				.limit(1)
			).run(as_dict=True)

			if item_data and item_data[0].variant_of:
				# Get the parent item's WC product ID
				parent_wc = (
					frappe.qb.from_(iws)
					.where(iws.parent == item_data[0].variant_of)
					.where(iws.woocommerce_server == wc_server_domain)
					.select(iws.woocommerce_id)
					.limit(1)
				).run(as_dict=True)
				if parent_wc:
					return parent_wc[0].woocommerce_id
		except Exception:
			pass
		return None

	def call_super_init(self, record: dict):
		super(Document, self).__init__(record)

	def after_load_from_db(self, record: dict):
		return record

	# ── List View ───────────────────────────
	@classmethod
	def get_list_of_records(cls, args) -> list[dict | Self]:
		"""Fetch paginated WooCommerce records for list/report views."""
		wc_api_list = cls._init_api()
		if not wc_api_list:
			return []

		wc_records_per_page_limit = 100
		per_page = (
			min(int(args["page_length"]), wc_records_per_page_limit)
			if args and "page_length" in args
			else wc_records_per_page_limit
		)
		offset = int(args["start"]) if args and "start" in args else 0
		params: dict = {"per_page": min(per_page + offset, wc_records_per_page_limit)}

		if args.get("filters"):
			params.update(get_wc_parameters_from_filters(args["filters"]))

		all_results: list = []
		total_processed = 0

		for wc_server in wc_api_list:
			if args.get("servers") and wc_server.woocommerce_server not in args["servers"]:
				continue

			current_offset = 0
			params["offset"] = current_offset

			try:
				endpoint = args.get("endpoint") or cls.resource
				response = wc_server.api.get(endpoint, params=params)
			except Exception as err:
				log_and_raise_error(err, error_text="get_list failed")

			if response.status_code != 200:
				log_and_raise_error(error_text="get_list failed", response=response)

			count_in_api = (
				int(response.headers["x-wp-total"])
				if "x-wp-total" in response.headers
				else len(response.json())
			)

			if count_in_api <= offset - total_processed:
				total_processed += count_in_api
				continue

			results = response.json()

			while True:
				if len(all_results) >= per_page:
					if args.get("as_doc"):
						return [frappe.get_doc(r) for r in all_results]
					return all_results

				start = max(0, offset - total_processed)
				end = min(len(results), per_page - len(all_results) + start)

				for record in results[start:end]:
					cls.pre_init_document(record, woocommerce_server_url=wc_server.woocommerce_server_url)
					cls.during_get_list_of_records(record, args)

				all_results.extend(results[start:end])
				total_processed += len(results)

				if len(results) < per_page:
					break

				current_offset += params["per_page"]
				params["offset"] = current_offset
				try:
					response = wc_server.api.get(cls.resource, params=params)
				except Exception as err:
					log_and_raise_error(err, error_text="get_list pagination failed")
				if response.status_code != 200:
					log_and_raise_error(error_text="get_list pagination failed", response=response)
				results = response.json()

		if args.get("as_doc"):
			return [frappe.get_doc(r) for r in all_results]
		return all_results

	@classmethod
	def during_get_list_of_records(cls, record: Document, args):
		return record

	@classmethod
	def get_count_of_records(cls, args) -> int:  # nosemgrep
		"""Return total record count from WooCommerce (for list view pagination)."""
		wc_api_list = cls._init_api()
		total_count = 0
		for wc_server in wc_api_list:
			try:
				response = wc_server.api.get(cls.resource)
			except Exception as err:
				log_and_raise_error(err, error_text="get_count failed")
			if response.status_code != 200:
				log_and_raise_error(error_text="get_count failed", response=response)
			if "x-wp-total" in response.headers:
				total_count += int(response.headers["x-wp-total"])
		return total_count

	@staticmethod
	def get_stats(args):  # nosemgrep
		pass

	# ── Create ──────────────────────────────
	def db_insert(self, *args, **kwargs):
		"""Create a new WooCommerce record via POST."""
		if not self.wc_api_list:
			self.init_api()

		self.current_wc_api = next(
			(api for api in self.wc_api_list if self.woocommerce_server == api.woocommerce_server),
			None,
		)

		record_data = self.to_dict()
		record = self.deserialize_attributes_of_type_dict_or_list(record_data)
		record = self.before_db_insert(record)

		endpoint = (
			f"{self.resource}/{self.parent_id}/{self.child_resource}"
			if getattr(self, "parent_id", None) and self.child_resource
			else self.resource
		)
		try:
			response = self.current_wc_api.api.post(endpoint, data=record)
		except Exception as err:
			log_and_raise_error(err, error_text="db_insert failed")

		if response.status_code != 201:
			log_and_raise_error(error_text="db_insert failed", response=response)

		self.woocommerce_id = response.json()["id"]
		self.woocommerce_date_modified = response.json().get("date_modified")

	def before_db_insert(self, record: dict):
		return record

	# ── Update ──────────────────────────────
	def db_update(self, *args, **kwargs):
		"""Update an existing WooCommerce record via PUT."""
		if not self.wc_api_list:
			self.init_api()

		record_data = self.to_dict()
		record = self.deserialize_attributes_of_type_dict_or_list(record_data)
		record = self.before_db_update(record)

		# Drop unchanged fields to minimise API payload
		record_data_before = self._doc_before_save.to_dict()
		record_before = self.deserialize_attributes_of_type_dict_or_list(record_data_before)
		if self.field_setter_map:
			for new_key, old_key in self.field_setter_map.items():
				record_before[old_key] = record_before.get(new_key)
		keys_to_drop = [
			k for k, v in record.items()
			if record_before.get(k) == v or str(record_before.get(k)) == str(v)
		]
		for k in keys_to_drop:
			record.pop(k)

		wc_server_domain, record_id = get_domain_and_id_from_woocommerce_record_name(self.name)
		self.current_wc_api = next(
			(api for api in self.wc_api_list if wc_server_domain in api.woocommerce_server_url),
			None,
		)

		endpoint = (
			f"{self.resource}/{getattr(self, 'parent_id', None)}/{self.child_resource}/{record_id}"
			if getattr(self, "parent_id", None) and self.child_resource
			else f"{self.resource}/{record_id}"
		)
		try:
			response = self.current_wc_api.api.put(endpoint, data=record)
		except Exception as err:
			log_and_raise_error(err, error_text="db_update failed")
		if response.status_code != 200:
			log_and_raise_error(error_text="db_update failed", response=response)

		self.woocommerce_date_modified = response.json().get("date_modified")
		self.after_db_update()

	def before_db_update(self, record: dict):
		return record

	def after_db_update(self):
		pass

	# ── Delete ──────────────────────────────
	def delete(self):
		frappe.throw(_("Deleting WooCommerce resources is not yet supported from ERPNext"))

	# ── Utilities ───────────────────────────
	def to_dict(self) -> dict:
		doc_dict = {f.fieldname: self.get(f.fieldname) for f in self.meta.fields}
		doc_dict["name"] = self.name
		return doc_dict

	def validate(self):
		"""Re-serialize JSON fields before Frappe validation."""
		json_fields = self.get_json_fields()
		for field in json_fields:
			value = self.get(field.fieldname)
			if isinstance(value, (list, dict)):
				self.set(field.fieldname, json.dumps(value))

	@classmethod
	def pre_init_document(cls, record: dict, woocommerce_server_url: str) -> dict:
		"""Prepare a raw WooCommerce dict for Frappe Document initialisation."""
		# Apply field renames
		if cls.field_setter_map:
			for new_key, old_key in cls.field_setter_map.items():
				record[new_key] = record.get(old_key)

		record.pop("_links", None)

		if "date_modified" in record:
			record["modified"] = record["date_modified"]
			record["woocommerce_date_created"] = record.get("date_created")
			record["woocommerce_date_created_gmt"] = record.get("date_created_gmt")
			record["woocommerce_date_modified"] = record.get("date_modified")
			record["woocommerce_date_modified_gmt"] = record.get("date_modified_gmt")

		server_domain = parse_domain_from_url(woocommerce_server_url)
		record["woocommerce_server"] = server_domain
		record["name"] = generate_woocommerce_record_name_from_domain_and_id(
			domain=server_domain, resource_id=record["id"]
		)
		record["doctype"] = cls.doctype
		cls.serialize_attributes_of_type_dict_or_list(record)
		return record

	@classmethod
	def serialize_attributes_of_type_dict_or_list(cls, obj: dict) -> dict:
		for field in cls.get_json_fields():
			if field.fieldname in obj:
				obj[field.fieldname] = json.dumps(obj[field.fieldname])
		return obj

	@classmethod
	def deserialize_attributes_of_type_dict_or_list(cls, obj: dict) -> dict:
		for field in cls.get_json_fields():
			if obj.get(field.fieldname):
				try:
					obj[field.fieldname] = json.loads(obj[field.fieldname])
				except (json.JSONDecodeError, TypeError):
					pass
		return obj

	@classmethod
	def get_json_fields(cls):
		return frappe.db.get_all(
			"DocField",
			{"parent": cls.doctype, "fieldtype": "JSON"},
			["name", "fieldname", "fieldtype"],
		)


# ────────────────────────────────────────────────────────────────
# Helper functions
# ────────────────────────────────────────────────────────────────

def generate_woocommerce_record_name_from_domain_and_id(
	domain: str, resource_id: int | str, delimiter: str = WC_RESOURCE_DELIMITER
) -> str:
	"""Build a Frappe document name from domain and WooCommerce record ID. E.g. 'shop.example.com~42'"""
	return f"{domain}{delimiter}{resource_id}"


def get_domain_and_id_from_woocommerce_record_name(
	name: str, delimiter: str = WC_RESOURCE_DELIMITER
) -> tuple[str, int]:
	"""Parse 'shop.example.com~42' → ('shop.example.com', 42)"""
	parts = name.split(delimiter)
	domain = parts[0]
	record_id = int(parts[1])
	return domain, record_id


def parse_domain_from_url(url: str) -> str:
	domain = urlparse(url).netloc
	if not domain:
		raise ValueError(_("Invalid WooCommerce Server URL: {0}").format(url))
	return domain


def get_wc_parameters_from_filters(filters: list) -> dict:
	"""
	Map Frappe list-view filter tuples to WooCommerce API query parameters.
	Supports: date_created, date_modified, id, name, status, customer_id, woocommerce_server.
	"""
	supported = {"date_created", "date_modified", "id", "name", "status", "woocommerce_server", "customer_id"}
	params: dict = {}

	for f in filters:
		field = f[1]
		op = f[2]
		val = f[3]

		if field not in supported:
			frappe.throw(_("Unsupported filter field: {0}").format(field))

		if field == "date_created":
			if op == "<":
				params["before"] = val
			elif op == ">":
				params["after"] = val
			elif op == "Between" and val:
				params["after"] = format_datetime(get_datetime(f"{val[0]} 00:00:00"), "yyyy-MM-dd HH:mm:ss")
				params["before"] = format_datetime(get_datetime(f"{val[1]} 00:00:00"), "yyyy-MM-dd HH:mm:ss")

		elif field == "date_modified":
			if op == "<":
				params["modified_before"] = val
			elif op == ">":
				params["modified_after"] = val
			elif op == "Between" and val:
				params["after"] = format_datetime(get_datetime(f"{val[0]} 00:00:00"), "yyyy-MM-dd HH:mm:ss")
				params["before"] = format_datetime(get_datetime(f"{val[1]} 00:00:00"), "yyyy-MM-dd HH:mm:ss")

		elif field == "id":
			if op == "=":
				params["include"] = [val]
			elif op == "in":
				params["include"] = ",".join(val)

		elif field == "name" and op == "like":
			params["search"] = val.strip("%")

		elif field == "customer_id" and op == "like":
			params["search"] = val.strip("%")

		elif field == "status" and op == "=":
			params["status"] = val

	return params


def log_and_raise_error(exception=None, error_text: str = None, response=None):
	"""Log an error to Frappe Error Log and throw to the user."""
	message = frappe.get_traceback() if exception else ""
	if error_text:
		message += f"\n{error_text}"
	if response is not None:
		message += (
			f"\nStatus: {response.status_code}"
			f"\nBody: {response.text}"
			f"\nURL: {response.request.url}"
			f"\nRequest Body: {response.request.body}"
		)
	log = frappe.log_error("WooCommerce Center Error", message)
	log_link = frappe.utils.get_link_to_form("Error Log", log.name)
	frappe.throw(
		msg=_("WooCommerce API error. See Error Log {0}").format(log_link),
		title=_("WooCommerce Center Error"),
	)
	if exception:
		raise exception
