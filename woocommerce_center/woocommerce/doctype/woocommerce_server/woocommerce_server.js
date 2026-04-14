// WooCommerce Center — WooCommerce Server Form JS
// Dynamic field options for Item/SO field mapping, webhook delivery URLs, manual sync buttons.
// Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com

frappe.ui.form.on("WooCommerce Server", {
    refresh: function (frm) {
        // Only list enabled, non-group warehouses
        frm.fields_dict.warehouses.get_query = function () {
            return { filters: { disabled: 0, is_group: 0 } };
        };

        // Populate Item field mapping options (only for saved docs)
        if (!frm.is_new()) {
            frappe.call({
                method: "get_item_docfields",
                doc: frm.doc,
                args: { doctype: "Item" },
                callback: function (r) {
                    if (!r.message) return;
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
                    if (!r.message) return;
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

            // ── Manual Sync Buttons ──
            if (frm.doc.enable_sync) {
                if (frm.doc.enable_order_sync) {
                    frm.add_custom_button(
                        __("Sync Orders Now"),
                        function () {
                            frappe.call({
                                method: "woocommerce_center.tasks.sync_sales_orders.sync_woocommerce_orders_modified_since",
                                freeze: true,
                                freeze_message: __("Syncing WooCommerce Orders..."),
                                callback: function () {
                                    frappe.msgprint(__("Order sync completed."));
                                },
                            });
                        },
                        __("Sync"),
                    );
                }

                if (frm.doc.enable_item_sync) {
                    frm.add_custom_button(
                        __("Sync Products Now"),
                        function () {
                            frappe.call({
                                method: "woocommerce_center.tasks.sync_items.sync_woocommerce_products_modified_since",
                                freeze: true,
                                freeze_message: __("Syncing WooCommerce Products..."),
                                callback: function () {
                                    frappe.msgprint(__("Product sync completed."));
                                },
                            });
                        },
                        __("Sync"),
                    );
                }

                if (frm.doc.enable_price_list_sync) {
                    frm.add_custom_button(
                        __("Sync Prices Now"),
                        function () {
                            frappe.call({
                                method: "woocommerce_center.tasks.sync_item_prices.run_item_price_sync_in_background",
                                freeze: true,
                                freeze_message: __("Syncing Item Prices..."),
                                callback: function () {
                                    frappe.msgprint(__("Price sync queued."));
                                },
                            });
                        },
                        __("Sync"),
                    );
                }

                if (frm.doc.enable_stock_level_synchronisation) {
                    frm.add_custom_button(
                        __("Sync Stock Now"),
                        function () {
                            frappe.call({
                                method: "woocommerce_center.tasks.stock_update.update_stock_levels_for_all_enabled_items_in_background",
                                freeze: true,
                                freeze_message: __("Syncing Stock Levels..."),
                                callback: function () {
                                    frappe.msgprint(__("Stock sync queued."));
                                },
                            });
                        },
                        __("Sync"),
                    );
                }
            }
        }

        // Render webhook delivery URLs
        render_webhook_delivery_urls(frm);
    },
});


function render_webhook_delivery_urls(frm) {
    const wrapper = frm.fields_dict.webhook_delivery_urls;
    if (!wrapper || !wrapper.$wrapper) return;

    if (frm.is_new()) {
        wrapper.$wrapper.html(
            '<p class="text-muted" style="margin-top:10px">Save the document to see webhook delivery URLs.</p>'
        );
        return;
    }

    // Use erpnext_site_url if set, otherwise fall back to browser origin
    let base = (frm.doc.erpnext_site_url || "").trim();
    if (!base) {
        base = window.location.origin;
    }
    // Remove trailing slash
    base = base.replace(/\/+$/, "");

    const endpoints = [
        { event: "order.created", fn: "create_order" },
        { event: "order.updated", fn: "update_order" },
        { event: "order.deleted", fn: "delete_order" },
        { event: "product.updated", fn: "update_product" },
    ];

    let rows = endpoints
        .map(
            (ep) =>
                `<tr>
            <td><code>${ep.event}</code></td>
            <td>
                <div class="d-flex align-items-center">
                    <code class="flex-grow-1" style="word-break:break-all">${base}/api/method/woocommerce_center.woocommerce_endpoint.${ep.fn}</code>
                    <button class="btn btn-xs btn-default ml-2 copy-url-btn"
                        data-url="${base}/api/method/woocommerce_center.woocommerce_endpoint.${ep.fn}"
                        title="Copy URL">
                        📋
                    </button>
                </div>
            </td>
        </tr>`
        )
        .join("");

    let site_note = frm.doc.erpnext_site_url
        ? ""
        : '<p class="text-warning" style="font-size:11px;margin-bottom:4px">⚠ No <b>ERPNext Site URL</b> set — showing browser URL. Set it above if WooCommerce needs to reach this site via a different domain (e.g. Cloudflare tunnel).</p>';

    let html = `
        <div class="webhook-urls-wrapper" style="margin-top:10px">
            <p class="text-muted" style="margin-bottom:8px">
                Use these URLs as <strong>Delivery URL</strong> when creating webhooks in
                WooCommerce → Settings → Advanced → Webhooks.
                Set the <strong>Secret</strong> to the value of the "Webhook Secret" field above.
            </p>
            ${site_note}
            <table class="table table-bordered table-sm" style="font-size:12px">
                <thead><tr><th style="width:140px">WC Event</th><th>Delivery URL</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;

    wrapper.$wrapper.html(html);

    // Copy-to-clipboard handler
    wrapper.$wrapper.find(".copy-url-btn").on("click", function () {
        const url = $(this).data("url");
        frappe.utils.copy_to_clipboard(url);
    });
}
