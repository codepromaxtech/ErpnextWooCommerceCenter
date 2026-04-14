// WooCommerce Center — WooCommerce Product Form JS
// Sync button and virtual doc intro for WooCommerce Product.
// Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com

frappe.ui.form.on("WooCommerce Product", {
    refresh: function (frm) {
        frm.add_custom_button(
            __("Sync this Item to ERPNext"),
            function () {
                frm.trigger("sync_product");
            },
            __("Actions"),
        );

        frm.set_intro(
            __(
                "Note: This is a Virtual Document. Saving changes on this document will update this resource on WooCommerce.",
            ),
            "orange",
        );
    },

    sync_product: function (frm) {
        frappe.dom.freeze(__("Sync Product with ERPNext..."));
        frappe.call({
            method: "woocommerce_center.tasks.sync_items.run_item_sync",
            args: { woocommerce_product_name: frm.doc.name },
            callback: function () {
                frappe.dom.unfreeze();
                frappe.show_alert(
                    { message: __("Sync completed successfully"), indicator: "green" },
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
