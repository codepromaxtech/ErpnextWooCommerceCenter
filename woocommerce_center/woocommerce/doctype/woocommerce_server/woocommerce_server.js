// WooCommerce Center — WooCommerce Server Form JS
// Webhook delivery URLs, manual sync buttons, field mapping options.
// Developer: CodeProMax Tech | Md. Al-Amin | codepromaxtech@gmail.com

frappe.ui.form.on("WooCommerce Server", {
    refresh: function (frm) {
        // Render webhook delivery URLs FIRST (most important, must always work)
        render_webhook_delivery_urls(frm);

        // Only for saved docs
        if (!frm.is_new()) {
            // ── Webhook Secret Buttons ──
            frm.add_custom_button(
                __("Generate Webhook Secret"),
                function () {
                    const arr = new Uint8Array(20);
                    crypto.getRandomValues(arr);
                    const secret = Array.from(arr, (b) =>
                        b.toString(16).padStart(2, "0"),
                    ).join("");
                    frm.set_value("webhook_secret", secret);
                    frm.dirty();
                    let d = new frappe.ui.Dialog({
                        title: __("Webhook Secret Generated"),
                        fields: [
                            {
                                fieldtype: "HTML",
                                fieldname: "secret_html",
                                options: `<p>${__("Copy this secret and paste it in each WooCommerce webhook:")}</p>
                                    <div style="margin:10px 0;padding:10px;background:#f5f5f5;border-radius:4px;border:1px solid #d1d8dd">
                                        <code style="font-size:14px;word-break:break-all" id="wc-secret-text">${secret}</code>
                                    </div>
                                    <p class="text-warning" style="font-size:12px;margin-top:8px">
                                        ⚠ Don't forget to <b>Save</b> this form and update the secret in your WooCommerce webhooks.
                                    </p>`,
                            },
                        ],
                        primary_action_label: __("Copy Secret"),
                        primary_action: function () {
                            frappe.utils.copy_to_clipboard(secret);
                            frappe.show_alert({
                                message: __("Secret copied!"),
                                indicator: "green",
                            });
                        },
                    });
                    d.show();
                },
                __("Webhook"),
            );

            frm.add_custom_button(
                __("Show Webhook Secret"),
                function () {
                    frappe.call({
                        method: "frappe.client.get_password",
                        args: {
                            doctype: "WooCommerce Server",
                            name: frm.doc.name,
                            fieldname: "webhook_secret",
                        },
                        callback: function (r) {
                            if (r && r.message) {
                                let secret = r.message;
                                let d = new frappe.ui.Dialog({
                                    title: __("Current Webhook Secret"),
                                    fields: [
                                        {
                                            fieldtype: "HTML",
                                            fieldname: "secret_html",
                                            options: `<div style="margin:10px 0;padding:10px;background:#f5f5f5;border-radius:4px;border:1px solid #d1d8dd">
                                                <code style="font-size:14px;word-break:break-all">${secret}</code>
                                            </div>`,
                                        },
                                    ],
                                    primary_action_label: __("Copy Secret"),
                                    primary_action: function () {
                                        frappe.utils.copy_to_clipboard(secret);
                                        frappe.show_alert({
                                            message: __("Secret copied!"),
                                            indicator: "green",
                                        });
                                    },
                                });
                                d.show();
                            } else {
                                frappe.msgprint(
                                    __(
                                        "No webhook secret set. Click 'Generate Webhook Secret' first.",
                                    ),
                                );
                            }
                        },
                    });
                },
                __("Webhook"),
            );

            // ── Manual Sync Buttons ──
            try {
                if (frm.doc.enable_sync) {
                    if (frm.doc.enable_item_sync) {
                        // Check product & order count from WooCommerce API
                        frm.add_custom_button(
                            __("🔢 Check Store Counts"),
                            function () {
                                frappe.call({
                                    method: "get_wc_product_count",
                                    doc: frm.doc,
                                    freeze: true,
                                    freeze_message: __("Querying WooCommerce store..."),
                                    callback: function (r) {
                                        if (r && r.message) {
                                            let c = r.message;
                                            frappe.msgprint({
                                                title: __("WooCommerce Store Summary"),
                                                message: `<p class="text-muted">Total items on your WooCommerce store:</p>
                                                    <table class="table table-bordered" style="margin:10px 0">
                                                    <tr><td><b>🛍️ Products</b></td><td>${c.products}</td></tr>
                                                    <tr><td><b>🛒 Orders</b></td><td>${c.orders}</td></tr>
                                                </table>`,
                                                indicator: "blue",
                                            });
                                        }
                                    },
                                });
                            },
                            __("Sync"),
                        );

                        // Full product sync (ALL products)
                        frm.add_custom_button(
                            __("📦 Sync All Products"),
                            function () {
                                frappe.confirm(
                                    __("This will fetch <b>ALL products</b> from your WooCommerce store and create/update items in ERPNext.<br><br>For large catalogs (1000+ products) this may take 10–30 minutes.<br><br>Continue?"),
                                    function () {
                                        frappe.call({
                                            method: "woocommerce_center.tasks.sync_items.sync_all_woocommerce_products",
                                            callback: function () {
                                                frappe.msgprint({
                                                    title: __("Full Product Sync Queued"),
                                                    message: __("A background job is now syncing all products from WooCommerce → ERPNext. You'll receive a notification when done.<br><br>Check <b>Background Jobs</b> for progress."),
                                                    indicator: "blue",
                                                });
                                            },
                                        });
                                    },
                                );
                            },
                            __("Sync"),
                        );

                        // Recent products (modified since last sync)
                        frm.add_custom_button(
                            __("📦 Sync Recent Products"),
                            function () {
                                frappe.call({
                                    method: "woocommerce_center.tasks.sync_items.sync_woocommerce_products_modified_since",
                                    freeze: true,
                                    freeze_message: __("Fetching recently modified products..."),
                                    callback: function () {
                                        frappe.msgprint({
                                            title: __("Recent Product Sync Complete"),
                                            message: __("Products modified since the last sync have been queued for processing."),
                                            indicator: "green",
                                        });
                                    },
                                });
                            },
                            __("Sync"),
                        );
                    }

                    if (frm.doc.enable_order_sync) {
                        // Full order sync (ALL orders)
                        frm.add_custom_button(
                            __("🛒 Sync All Orders"),
                            function () {
                                frappe.confirm(
                                    __("This will fetch <b>ALL orders</b> from your WooCommerce store and create/update Sales Orders in ERPNext.<br><br>For stores with many orders this may take 10–30 minutes.<br><br>Continue?"),
                                    function () {
                                        frappe.call({
                                            method: "woocommerce_center.tasks.sync_sales_orders.sync_all_woocommerce_orders",
                                            callback: function () {
                                                frappe.msgprint({
                                                    title: __("Full Order Sync Queued"),
                                                    message: __("A background job is now syncing all orders from WooCommerce → ERPNext. You'll receive a notification when done.<br><br>Check <b>Background Jobs</b> for progress."),
                                                    indicator: "blue",
                                                });
                                            },
                                        });
                                    },
                                );
                            },
                            __("Sync"),
                        );

                        // Recent orders (modified since last sync)
                        frm.add_custom_button(
                            __("🛒 Sync Recent Orders"),
                            function () {
                                frappe.call({
                                    method: "woocommerce_center.tasks.sync_sales_orders.sync_woocommerce_orders_modified_since",
                                    freeze: true,
                                    freeze_message: __("Fetching recently modified orders..."),
                                    callback: function () {
                                        frappe.msgprint({
                                            title: __("Recent Order Sync Complete"),
                                            message: __("Orders modified since the last sync have been queued for processing."),
                                            indicator: "green",
                                        });
                                    },
                                });
                            },
                            __("Sync"),
                        );
                    }

                    if (frm.doc.enable_price_list_sync) {
                        frm.add_custom_button(
                            __("💰 Sync Prices"),
                            function () {
                                frappe.call({
                                    method: "woocommerce_center.tasks.sync_item_prices.run_item_price_sync_in_background",
                                    freeze: true,
                                    freeze_message: __("Syncing item prices..."),
                                    callback: function () {
                                        frappe.msgprint({
                                            title: __("Price Sync Queued"),
                                            message: __("Item prices are being synced in the background."),
                                            indicator: "green",
                                        });
                                    },
                                });
                            },
                            __("Sync"),
                        );
                    }

                    if (frm.doc.enable_stock_level_synchronisation) {
                        frm.add_custom_button(
                            __("📊 Sync Stock Levels"),
                            function () {
                                frappe.confirm(
                                    __("This will push current ERPNext stock levels to WooCommerce for all enabled items.<br><br>Continue?"),
                                    function () {
                                        frappe.call({
                                            method: "woocommerce_center.tasks.stock_update.update_stock_levels_for_all_enabled_items_in_background",
                                            freeze: true,
                                            freeze_message: __("Queuing stock level updates..."),
                                            callback: function () {
                                                frappe.msgprint({
                                                    title: __("Stock Sync Queued"),
                                                    message: __("Stock levels are being pushed from ERPNext → WooCommerce in the background."),
                                                    indicator: "green",
                                                });
                                            },
                                        });
                                    },
                                );
                            },
                            __("Sync"),
                        );
                    }
                }
            } catch (e) {
                console.warn("WC Center: sync buttons setup failed", e);
            }

            // ── Field Mapping Options ──
            try {
                frappe.call({
                    method: "get_item_docfields",
                    doc: frm.doc,
                    args: { doctype: "Item" },
                    callback: function (r) {
                        if (!r || !r.message) return;
                        r.message.sort((a, b) =>
                            (a.label || "").localeCompare(b.label || ""),
                        );
                        const options = r.message
                            .map((f) => `${f.fieldname} | ${f.label}`)
                            .join("\n");
                        if (frm.fields_dict.item_field_map) {
                            frm.fields_dict.item_field_map.grid.update_docfield_property(
                                "erpnext_field_name",
                                "options",
                                options,
                            );
                        }
                    },
                });
            } catch (e) {
                console.warn("WC Center: Item field map setup failed", e);
            }

            try {
                frappe.call({
                    method: "get_item_docfields",
                    doc: frm.doc,
                    args: { doctype: "Sales Order Item" },
                    callback: function (r) {
                        if (!r || !r.message) return;
                        r.message.sort((a, b) =>
                            (a.label || "").localeCompare(b.label || ""),
                        );
                        const options = r.message
                            .map((f) => `${f.fieldname} | ${f.label}`)
                            .join("\n");
                        if (frm.fields_dict.order_line_item_field_map) {
                            frm.fields_dict.order_line_item_field_map.grid.update_docfield_property(
                                "erpnext_field_name",
                                "options",
                                options,
                            );
                        }
                    },
                });
            } catch (e) {
                console.warn(
                    "WC Center: SO Item field map setup failed",
                    e,
                );
            }
        }

        // Only list enabled, non-group warehouses
        try {
            if (frm.fields_dict.warehouses) {
                frm.fields_dict.warehouses.get_query = function () {
                    return { filters: { disabled: 0, is_group: 0 } };
                };
            }
        } catch (e) {
            console.warn("WC Center: warehouses query setup failed", e);
        }
    },
});

function render_webhook_delivery_urls(frm) {
    const wrapper = frm.fields_dict.webhook_delivery_urls;
    if (!wrapper || !wrapper.$wrapper) {
        console.warn("WC Center: webhook_delivery_urls field not found");
        return;
    }

    if (frm.is_new()) {
        wrapper.$wrapper.html(
            '<p class="text-muted" style="margin-top:10px">Save the document to see webhook delivery URLs.</p>',
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
        </tr>`,
        )
        .join("");

    let site_note = frm.doc.erpnext_site_url
        ? ""
        : `<div class="alert alert-warning" style="font-size:12px;padding:8px 12px;margin-bottom:8px">
            ⚠ No <b>ERPNext Site URL</b> set — showing browser URL. Set it above if WooCommerce
            needs to reach this site via a different domain (e.g. Cloudflare tunnel).
           </div>`;

    let html = `
        <div class="webhook-urls-wrapper" style="margin-top:4px">
            <p class="text-muted" style="margin-bottom:8px;font-size:12px">
                Create <b>4 webhooks</b> in WooCommerce → Settings → Advanced → Webhooks.
                For each, copy the <b>Delivery URL</b> below and set the <b>Secret</b> to the
                Webhook Secret field above. Use <b>API Version: WP REST API Integration v3</b>.
            </p>
            ${site_note}
            <table class="table table-bordered table-sm" style="font-size:12px;margin-bottom:0">
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
