// WooCommerce Center — WooCommerce Server Form JS
// Dynamic field options for Item/SO field mapping, webhook delivery URLs.
// Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com

frappe.ui.form.on("WooCommerce Server", {
    refresh: function (frm) {
        // Only list enabled, non-group warehouses
        frm.fields_dict.warehouses.get_query = function () {
            return { filters: { disabled: 0, is_group: 0 } };
        };

        // Populate Item field mapping options
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

    const base = window.location.origin;
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

    let html = `
        <div class="webhook-urls-wrapper" style="margin-top:10px">
            <p class="text-muted" style="margin-bottom:8px">
                Use these URLs as <strong>Delivery URL</strong> when creating webhooks in
                WooCommerce → Settings → Advanced → Webhooks.
                Set the <strong>Secret</strong> to the value of the "Webhook Secret" field above.
            </p>
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

