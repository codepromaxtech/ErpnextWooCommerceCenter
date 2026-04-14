// WooCommerce Center — Item Form JS
// Adds WooCommerce sync action buttons to Item form.
// Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com

frappe.ui.form.on("Item", {
    refresh: function (frm) {
        // Sync Stock Levels
        frm.add_custom_button(
            __("Sync this Item's Stock Levels to WooCommerce"),
            function () {
                frm.trigger("sync_item_stock");
            },
            __("Actions"),
        );

        // Sync Price
        frm.add_custom_button(
            __("Sync this Item's Price to WooCommerce"),
            function () {
                frm.trigger("sync_item_price");
            },
            __("Actions"),
        );

        // Sync Item
        frm.add_custom_button(
            __("Sync this Item with WooCommerce"),
            function () {
                frm.trigger("sync_item");
            },
            __("Actions"),
        );
    },

    sync_item_stock: function (frm) {
        frappe.dom.freeze(__("Sync Item Stock with WooCommerce..."));
        frappe.call({
            method:
                "woocommerce_center.tasks.stock_update.update_stock_levels_on_woocommerce_site",
            args: { item_code: frm.doc.name },
            callback: function () {
                frappe.dom.unfreeze();
                frappe.show_alert(
                    {
                        message: __(
                            "Synchronised stock level to WooCommerce for enabled servers",
                        ),
                        indicator: "green",
                    },
                    5,
                );
                frm.reload_doc();
            },
            error: () => {
                frappe.dom.unfreeze();
                frappe.show_alert(
                    {
                        message: __(
                            "There was an error processing the request. See Error Log.",
                        ),
                        indicator: "red",
                    },
                    5,
                );
            },
        });
    },

    sync_item_price: function (frm) {
        frappe.dom.freeze(__("Sync Item Price with WooCommerce..."));
        frappe.call({
            method: "woocommerce_center.tasks.sync_item_prices.run_item_price_sync",
            args: { item_code: frm.doc.name },
            callback: function () {
                frappe.dom.unfreeze();
                frappe.show_alert(
                    {
                        message: __("Synchronised item price to WooCommerce"),
                        indicator: "green",
                    },
                    5,
                );
                frm.reload_doc();
            },
            error: () => {
                frappe.dom.unfreeze();
                frappe.show_alert(
                    {
                        message: __(
                            "There was an error processing the request. See Error Log.",
                        ),
                        indicator: "red",
                    },
                    5,
                );
            },
        });
    },

    sync_item: function (frm) {
        frappe.dom.freeze(__("Sync Item with WooCommerce..."));
        frappe.call({
            method: "woocommerce_center.tasks.sync_items.run_item_sync",
            args: { item_code: frm.doc.name },
            callback: function () {
                frappe.dom.unfreeze();
                frappe.show_alert(
                    {
                        message: __("Sync completed successfully"),
                        indicator: "green",
                    },
                    5,
                );
                frm.reload_doc();
            },
            error: () => {
                frappe.dom.unfreeze();
                frappe.show_alert(
                    {
                        message: __(
                            "There was an error processing the request. See Error Log.",
                        ),
                        indicator: "red",
                    },
                    5,
                );
            },
        });
    },
});

frappe.ui.form.on("Item WooCommerce Server", {
    view_product: function (frm, cdt, cdn) {
        let current_row_doc = locals[cdt][cdn];
        frappe.set_route(
            "Form",
            "WooCommerce Product",
            `${current_row_doc.woocommerce_server}~${current_row_doc.woocommerce_id}`,
        );
    },
});
