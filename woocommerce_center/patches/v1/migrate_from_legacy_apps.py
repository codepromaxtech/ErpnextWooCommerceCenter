"""
WooCommerce Center — Migration Patch v1
Migrates data from legacy apps (woocommerce_fusion, woocommerce_integration,
woocommerce_connector / ErpnextWooCommerceConnector) into WooCommerce Center doctypes.

Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com

Run: bench --site <site> migrate
This patch is idempotent — safe to run multiple times.
"""

import frappe


def execute():
	"""Migrate data from legacy WooCommerce apps into WooCommerce Center."""

	# ── 1. Migrate WooCommerce Server records ─────────────────
	migrate_woocommerce_servers()

	# ── 2. Migrate WooCommerce Integration Settings ────────────
	migrate_integration_settings()

	# ── 3. Migrate Item WooCommerce Server child table data ───
	migrate_item_woocommerce_servers()

	frappe.db.commit()
	frappe.clear_cache()
	print("✅ WooCommerce Center migration patch completed successfully.")


def migrate_woocommerce_servers():
	"""Copy WooCommerce Server records from legacy app if its table exists."""
	legacy_tables = [
		"tabWooCommerce Server",  # woocommerce_fusion
	]

	for table_name in legacy_tables:
		if not frappe.db.table_exists(table_name):
			continue

		# Read all existing servers
		legacy_servers = frappe.db.sql(f"SELECT * FROM `{table_name}`", as_dict=True)
		for server_data in legacy_servers:
			if frappe.db.exists("WooCommerce Server", server_data.get("name")):
				print(f"  ⏭ WooCommerce Server '{server_data['name']}' already exists, skipping.")
				continue

			try:
				doc = frappe.new_doc("WooCommerce Server")
				# Copy all matching fields
				for key, value in server_data.items():
					if key in ("doctype", "docstatus", "idx", "owner", "creation", "modified", "modified_by"):
						continue
					if hasattr(doc, key):
						setattr(doc, key, value)

				doc.flags.ignore_mandatory = True
				doc.flags.ignore_validate = True
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
				print(f"  ✅ Migrated WooCommerce Server: {doc.name}")
			except Exception as e:
				print(f"  ❌ Failed to migrate WooCommerce Server '{server_data.get('name')}': {e}")
				frappe.log_error("WooCommerce Migration Error", frappe.get_traceback())


def migrate_integration_settings():
	"""Migrate WooCommerce Integration Settings singleton."""
	legacy_table = "tabWooCommerce Integration Settings"
	if not frappe.db.table_exists(legacy_table):
		return

	legacy_settings = frappe.db.sql(f"SELECT * FROM `{legacy_table}` LIMIT 1", as_dict=True)
	if not legacy_settings:
		return

	legacy_data = legacy_settings[0]
	try:
		doc = frappe.get_doc("WooCommerce Integration Settings")
		for key, value in legacy_data.items():
			if key in ("doctype", "docstatus", "name", "owner", "creation", "modified", "modified_by"):
				continue
			if hasattr(doc, key) and value:
				setattr(doc, key, value)
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
		print("  ✅ Migrated WooCommerce Integration Settings")
	except Exception as e:
		print(f"  ❌ Failed to migrate Integration Settings: {e}")
		frappe.log_error("WooCommerce Migration Error", frappe.get_traceback())


def migrate_item_woocommerce_servers():
	"""Migrate Item WooCommerce Server child table rows."""
	legacy_table = "tabItem WooCommerce Server"
	if not frappe.db.table_exists(legacy_table):
		return

	legacy_rows = frappe.db.sql(f"SELECT * FROM `{legacy_table}`", as_dict=True)
	migrated = 0
	for row_data in legacy_rows:
		parent = row_data.get("parent")
		if not parent or not frappe.db.exists("Item", parent):
			continue

		# Check if this link already exists
		existing = frappe.db.exists(
			"Item WooCommerce Server",
			{
				"parent": parent,
				"woocommerce_server": row_data.get("woocommerce_server"),
				"woocommerce_id": row_data.get("woocommerce_id"),
			},
		)
		if existing:
			continue

		try:
			item = frappe.get_doc("Item", parent)
			row = item.append("woocommerce_servers")
			row.woocommerce_server = row_data.get("woocommerce_server")
			row.woocommerce_id = row_data.get("woocommerce_id")
			row.enabled = row_data.get("enabled", 1)
			row.woocommerce_last_sync_hash = row_data.get("woocommerce_last_sync_hash")
			item.flags.ignore_mandatory = True
			item.flags.created_by_sync = True
			item.save(ignore_permissions=True)
			migrated += 1
		except Exception as e:
			print(f"  ❌ Failed to migrate Item WC Server link for '{parent}': {e}")
			frappe.log_error("WooCommerce Migration Error", frappe.get_traceback())

	if migrated:
		print(f"  ✅ Migrated {migrated} Item WooCommerce Server links")
