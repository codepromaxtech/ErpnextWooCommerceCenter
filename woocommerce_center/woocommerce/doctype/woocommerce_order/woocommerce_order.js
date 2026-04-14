// WooCommerce Center — WooCommerce Order Form JS
// Sync button and virtual doc intro for WooCommerce Order.
// Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com

frappe.ui.form.on("WooCommerce Order", {
    refresh: function (frm) {
        frm.add_custom_button(
            __("Sync this Order to ERPNext"),
            function () {
                frm.trigger("sync_sales_order");
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

    sync_sales_order: function (frm) {
        frappe.dom.freeze(__("Sync Order with ERPNext..."));
        frappe.call({
            method:
                "woocommerce_center.tasks.sync_sales_orders.run_sales_order_sync",
            args: { woocommerce_order_name: frm.doc.name },
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
