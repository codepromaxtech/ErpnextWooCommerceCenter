// WooCommerce Center — Sales Order Form JS
// Adds WooCommerce-specific buttons and sync actions to Sales Order form.
// Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com

frappe.ui.form.on("Sales Order", {
    refresh: function (frm) {
        if (frm.doc.woocommerce_id) {
            // Open in WooCommerce
            frm.add_custom_button(
                __("Open in WooCommerce"),
                function () {
                    frappe.db.get_value(
                        "WooCommerce Server",
                        frm.doc.woocommerce_server,
                        "woocommerce_server_url",
                        (values) => {
                            window.open(
                                values.woocommerce_server_url +
                                `/wp-admin/post.php?post=${frm.doc.woocommerce_id}&action=edit`,
                                "_blank",
                            );
                        },
                    );
                },
                __("Actions"),
            );

            // Sync this order
            frm.add_custom_button(
                __("Sync this Order with WooCommerce"),
                function () {
                    frm.trigger("sync_sales_order");
                },
                __("Actions"),
            );

            // Shipment Tracking
            frm.add_custom_button(
                __("Edit WooCommerce Shipment Trackings"),
                function () {
                    frm.trigger("prompt_user_for_shipment_trackings");
                },
                __("Actions"),
            );
        }

        if (
            frm.doc.woocommerce_id &&
            frm.doc.woocommerce_server &&
            ["Shipped", "Delivered"].includes(frm.doc.woocommerce_status)
        ) {
            frm.trigger("load_shipment_trackings_table");
        } else {
            frm.doc.woocommerce_shipment_trackings = [];
            frm.set_df_property("woocommerce_shipment_tracking_html", "options", " ");
        }
    },

    sync_sales_order: function (frm) {
        frappe.dom.freeze(__("Sync Order with WooCommerce..."));
        frappe.call({
            method: "woocommerce_center.tasks.sync_sales_orders.run_sales_order_sync",
            args: { sales_order_name: frm.doc.name },
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

    woocommerce_status: function (frm) {
        frappe.confirm(
            "Changing the status will update the order status on WooCommerce. Do you want to continue?",
            function () {
                frm.save("Update", function () {
                    if (!frm.doc.__unsaved) {
                        frappe.dom.freeze(
                            __("Updating Order status on WooCommerce..."),
                        );
                        frappe.call({
                            method:
                                "woocommerce_center.tasks.sync_sales_orders.run_sales_order_sync",
                            args: { sales_order_name: frm.doc.name },
                            btn: $(".primary-action"),
                            callback: () => {
                                frappe.dom.unfreeze();
                                frappe.show_alert(
                                    {
                                        message: __(
                                            "Updated WooCommerce Order successfully",
                                        ),
                                        indicator: "green",
                                    },
                                    5,
                                );
                            },
                            error: (r) => {
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
                                console.error(r);
                            },
                        });
                    }
                });
            },
            function () {
                frm.reload_doc();
            },
        );
    },

    load_shipment_trackings_table: function (frm) {
        frm.set_df_property(
            "woocommerce_shipment_tracking_html",
            "options",
            "🚚 <i>Loading Shipments...</i><br><br><br><br>",
        );
        frm.refresh_field("woocommerce_shipment_tracking_html");
        frappe.call({
            method:
                "woocommerce_center.overrides.selling.sales_order.get_woocommerce_order_shipment_trackings",
            args: { doc: frm.doc },
            callback: function (r) {
                if (r.message) {
                    frappe.show_alert({
                        indicator: "green",
                        message: __("Retrieved WooCommerce Shipment Trackings"),
                    });
                    frm.doc.woocommerce_shipment_trackings = r.message;

                    let trackingsHTML =
                        `<b>WooCommerce Shipments:</b><br><table class="table table-striped">` +
                        `<tr><th>Date Shipped</th><th>Provider</th><th>Tracking Number</th>`;
                    frm.doc.woocommerce_shipment_trackings.forEach((tracking) => {
                        trackingsHTML +=
                            `<tr><td>${tracking.date_shipped}</td>` +
                            `<td>${tracking.tracking_provider}</td>` +
                            `<td><a href="${tracking.tracking_link}">${tracking.tracking_number}</a></td></tr>`;
                    });
                    trackingsHTML += `</table>`;
                    frm.set_df_property(
                        "woocommerce_shipment_tracking_html",
                        "options",
                        trackingsHTML,
                    );
                    frm.refresh_field("woocommerce_shipment_tracking_html");
                } else {
                    frm.set_df_property(
                        "woocommerce_shipment_tracking_html",
                        "options",
                        "",
                    );
                    frm.refresh_field("woocommerce_shipment_tracking_html");
                }
            },
        });
    },

    prompt_user_for_shipment_trackings: function (frm) {
        frappe.call({
            method:
                "woocommerce_center.woocommerce.doctype.woocommerce_server" +
                ".woocommerce_server.get_woocommerce_shipment_providers",
            args: { woocommerce_server: frm.doc.woocommerce_server },
            callback: function (r) {
                const trackingProviders = r.message;
                let shipment_trackings = frm.doc.woocommerce_shipment_trackings || [];

                let d = new frappe.ui.Dialog({
                    title: __("Enter Shipment Tracking details"),
                    fields: [
                        {
                            fieldname: "tracking_id",
                            fieldtype: "Data",
                            label: "Tracking ID",
                            read_only: 1,
                            default:
                                shipment_trackings.length > 0
                                    ? shipment_trackings[0].tracking_id
                                    : null,
                        },
                        {
                            fieldname: "tracking_provider",
                            fieldtype: "Select",
                            label: "Tracking Provider",
                            reqd: 1,
                            options: trackingProviders,
                            default:
                                shipment_trackings.length > 0
                                    ? shipment_trackings[0].tracking_provider
                                    : null,
                        },
                        {
                            fieldname: "tracking_number",
                            fieldtype: "Data",
                            label: "Tracking Number",
                            reqd: 1,
                            default:
                                shipment_trackings.length > 0
                                    ? shipment_trackings[0].tracking_number
                                    : null,
                        },
                        {
                            fieldname: "tracking_link",
                            fieldtype: "Data",
                            label: "Tracking Link",
                            read_only: 1,
                            default:
                                shipment_trackings.length > 0
                                    ? shipment_trackings[0].tracking_link
                                    : null,
                        },
                        {
                            fieldname: "date_shipped",
                            fieldtype: "Date",
                            label: "Date Shipped",
                            reqd: 1,
                            default:
                                shipment_trackings.length > 0
                                    ? shipment_trackings[0].date_shipped
                                    : null,
                        },
                    ],
                    primary_action: function () {
                        let values = d.get_values();
                        let shipment_tracking = {
                            tracking_id: null,
                            tracking_provider: values.tracking_provider,
                            tracking_link: null,
                            tracking_number: values.tracking_number,
                            date_shipped: values.date_shipped,
                        };
                        d.hide();
                        frm.doc.woocommerce_shipment_trackings = [shipment_tracking];
                        frm.trigger("update_shipment_trackings");
                    },
                    primary_action_label: __("Submit and Sync to WooCommerce"),
                });
                d.show();
            },
        });
    },

    update_shipment_trackings: function (frm) {
        frappe.call({
            method:
                "woocommerce_center.overrides.selling.sales_order.update_woocommerce_order_shipment_trackings",
            args: {
                doc: frm.doc,
                shipment_trackings: frm.doc.woocommerce_shipment_trackings,
            },
            callback: function () {
                frm.reload_doc();
            },
        });
    },
});
