"""
WooCommerce Center — WooCommerce Product controller.
Virtual doctype backed by WooCommerce REST API.
Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com
Ported and extended from woocommerce_fusion (Starktail).
"""

import json
from dataclasses import dataclass
from typing import ClassVar

from woocommerce_center.woocommerce.woocommerce_api import WooCommerceAPI, WooCommerceResource


@dataclass
class WooCommerceProductAPI(WooCommerceAPI):
	"""API configuration for WooCommerce Products."""
	pass


class WooCommerceProduct(WooCommerceResource):
	"""Virtual doctype for WooCommerce Products — supports simple, variable, and variation types."""

	doctype = "WooCommerce Product"
	resource: str = "products"
	child_resource: str = "variations"
	field_setter_map: ClassVar[dict[str, str]] = {
		"woocommerce_name": "name",
		"woocommerce_id": "id",
	}

	@staticmethod
	def get_list(args):
		products = WooCommerceProduct.get_list_of_records(args)

		# Extend with product variants (variations)
		products_with_variants = [
			(product.get("id"), product.get("woocommerce_name"))
			for product in products
			if product.get("type") == "variable"
		]
		for id, woocommerce_name in products_with_variants:
			args["endpoint"] = f"products/{id}/variations"
			args["metadata"] = {"parent_woocommerce_name": woocommerce_name}
			variants = WooCommerceProduct.get_list_of_records(args)
			products.extend(variants)

		return products

	def after_load_from_db(self, product: dict):
		product.pop("name", None)
		product = self.set_title(product)
		return product

	@classmethod
	def during_get_list_of_records(cls, product: dict, args):
		if product.get("parent_id"):
			product["type"] = "variation"

			if variation_name := cls.get_variation_name(product, args):
				args["metadata"]["woocommerce_name"] = variation_name
				product = cls.override_woocommerce_name(product, variation_name)

		product = cls.set_title(product, args)
		return product

	@staticmethod
	def set_title(product: dict, args=None):
		if args and (metadata := args.get("metadata")) and (set_name := metadata.get("woocommerce_name")):
			product["title"] = set_name
		elif wc_name := product.get("woocommerce_name"):
			# SKU is already the item_code in ERPNext — no need to prefix the display name.
			product["title"] = wc_name
		else:
			product["title"] = product.get("woocommerce_id", "Unknown")
		return product


	@staticmethod
	def override_woocommerce_name(product: dict, name: str):
		product["woocommerce_name"] = name
		return product

	@staticmethod
	def get_variation_name(product: dict, args):
		if (
			product.get("type") == "variation"
			and (metadata := args.get("metadata"))
			and (attributes := product.get("attributes"))
			and (parent_wc_name := metadata.get("parent_woocommerce_name"))
		):
			attr_values = [attr["option"] for attr in json.loads(attributes)]
			return parent_wc_name + " - " + ", ".join(attr_values)
		return None

	@staticmethod
	def get_count(args) -> int:
		return WooCommerceProduct.get_count_of_records(args)

	def before_db_insert(self, product: dict):
		return self.clean_up_product_before_write(product)

	def before_db_update(self, product: dict):
		return self.clean_up_product_before_write(product)

	def after_db_update(self):
		pass

	@staticmethod
	def clean_up_product_before_write(product):
		"""Ensure product data is in the correct format for the WC API."""
		product["weight"] = str(product.get("weight", ""))
		product["regular_price"] = str(product.get("regular_price", ""))

		if product.get("sale_price") and float(product["sale_price"]) > 0:
			product["sale_price"] = str(product["sale_price"])
		else:
			product.pop("sale_price", None)

		product["name"] = str(product.get("woocommerce_name", ""))
		product.pop("related_ids", None)

		return product
