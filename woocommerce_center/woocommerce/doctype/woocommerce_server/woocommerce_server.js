// WooCommerce Center — WooCommerce Server Form JS
// Dynamic field options for Item/SO field mapping, webhook config dialog, WC status list.
// Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com

frappe.ui.form.on("WooCommerce Server", {
    refresh: function (frm) {
        // Only list enabled, non-group warehouses
        frm.fields_dict.warehouses.get_query = function () {
            return { filters: { disabled: 0, is_group: 0 } };
        };

        // Populate Item field mapping options
        frappe.call({
            method: "get_item_docfields",
            doc: frm.doc,
            args: { doctype: "Item" },
            callback: function (r) {
                r.message.sort((a, b) =>
                    (a.label || "").localeCompare(b.label || ""),
                );
                const options = r.message
                    .map((f) => `${f.fieldname} | ${f.label}`)
                    .join("\n");
                frm.fields_dict.item_field_map.grid.update_docfield_property(
                    "erpnext_field_name",
                    "options",
                    options,
                );
            },
        });

        // Populate Sales Order Item field mapping options
        frappe.call({
            method: "get_item_docfields",
            doc: frm.doc,
            args: { doctype: "Sales Order Item" },
            callback: function (r) {
                r.message.sort((a, b) =>
                    (a.label || "").localeCompare(b.label || ""),
                );
                const options = r.message
                    .map((f) => `${f.fieldname} | ${f.label}`)
                    .join("\n");
                frm.fields_dict.order_line_item_field_map.grid.update_docfield_property(
                    "erpnext_field_name",
                    "options",
                    options,
                );
            },
        });

        // Populate WooCommerce Order Status options
        if (
            frm.doc.enable_so_status_sync &&
            !frm.fields_dict.sales_order_status_map.grid.get_docfield(
                "woocommerce_sales_order_status",
            ).options
        ) {
            frm.trigger("get_woocommerce_order_status_list");
        }

        // Experimental warning for SO Status Sync
        let warningHTML = `
      <div class="form-message red">
        <div>
          ${__("This setting is Experimental. Monitor your Error Log after enabling this setting")}
        </div>
      </div>`;
        frm.set_df_property(
            "enable_so_status_sync_warning_html",
            "options",
            warningHTML,
        );
        frm.refresh_field("enable_so_status_sync_warning_html");
    },

    enable_so_status_sync: function (frm) {
        if (
            frm.doc.enable_so_status_sync &&
            !frm.fields_dict.sales_order_status_map.grid.get_docfield(
                "woocommerce_sales_order_status",
            ).options
        ) {
            frm.trigger("get_woocommerce_order_status_list");
        }
    },

    get_woocommerce_order_status_list: function (frm) {
        frappe.call({
            method: "get_woocommerce_order_status_list",
            doc: frm.doc,
            callback: function (r) {
                const options = r.message.join("\n");
                frm.fields_dict.sales_order_status_map.grid.update_docfield_property(
                    "woocommerce_sales_order_status",
                    "options",
                    options,
                );
            },
        });
    },

    view_webhook_config: function (frm) {
        let d = new frappe.ui.Dialog({
            title: __("WooCommerce Webhook Settings"),
            fields: [
                {
                    label: __("Status"),
                    fieldname: "status",
                    fieldtype: "Data",
                    default: "Active",
                    read_only: 1,
                },
                {
                    label: __("Topic"),
                    fieldname: "topic",
                    fieldtype: "Data",
                    default: "Order created",
                    read_only: 1,
                },
                {
                    label: __("Delivery URL"),
                    fieldname: "url",
                    fieldtype: "Data",
                    default:
                        "<site url here>/api/method/woocommerce_center.woocommerce_endpoint.create_order",
                    read_only: 1,
                },
                {
                    label: __("Secret"),
                    fieldname: "secret",
                    fieldtype: "Code",
                    default: frm.doc.secret,
                    read_only: 1,
                },
                {
                    label: __("API Version"),
                    fieldname: "api_version",
                    fieldtype: "Data",
                    default: "WP REST API Integration v3",
                    read_only: 1,
                },
            ],
            size: "large",
            primary_action_label: __("OK"),
            primary_action() {
                d.hide();
            },
        });
        d.show();
    },
});
