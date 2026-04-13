// Copyright (c) 2024, ALYF GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on("WooCommerce Setup", {
  onload: function (frm) {
    if (frm.doc.__onload && frm.doc.__onload.sales_order_series) {
      set_field_options(
        "sales_order_series",
        frm.doc.__onload.sales_order_series
      );
    }
  },

  refresh: function (frm) {
    frm.METHOD_PATH =
      "woocommerce_integration.woocommerce.doctype.woocommerce_setup.woocommerce_setup";
    frm.events.add_button_generate_secret(frm);
    frm.events.add_button_to_sync_stock(frm);
    frm.events.add_button_to_sync_order(frm);
  },

  add_button_generate_secret(frm) {
    frm.add_custom_button(__("Generate Secret"), () => {
      frappe.confirm(
        __(
          "This will require resetting the webhook secret in your WooCommerce instance."
        ),
        () => {
          frm.call("generate_secret").then(() => frm.reload_doc());
        }
      );
    });
  },

  add_button_to_sync_stock(frm) {
    if (!frm.doc.enable_stock_sync) return;

    frm.add_custom_button(
      __("Stock to WooCommerce"),
      () =>
        frappe.call({
          method: frm.METHOD_PATH + ".sync_stock",
          freeze: true,
          freeze_message: __("Syncing stock ..."),
        }),
      __("Sync")
    );
  },

  add_button_to_sync_order(frm) {
    if (!frm.doc.enable_order_sync) return;

    frm.add_custom_button(
      __("Orders from WooCommerce"),
      () =>
        frappe.call({
          method: frm.METHOD_PATH + ".sync_orders",
          freeze: true,
          freeze_message: __("Syncing orders ..."),
        }),
      __("Sync")
    );
  },
});
