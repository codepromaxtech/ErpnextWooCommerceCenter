# WooCommerce Center

**All-in-one WooCommerce ↔ ERPNext Connector**

Multi-site, bidirectional synchronisation of orders, products, stock, prices, payments, and webhooks.

> Developer: **CodeProMax Tech** | Md. Al-Amin | codepromaxtech@gmail.com

---

## Features

| Feature | Direction | Details |
|---|---|---|
| **Product / Item Sync** | ↔ Bidirectional | Create, update, field mapping via JSONPath, variant/attribute support |
| **Sales Order Sync** | ↔ Bidirectional | Hash-based change detection, status mapping, auto-naming |
| **Stock Level Sync** | → WooCommerce | Multi-warehouse, variant support, reserved stock subtraction |
| **Item Price Sync** | → WooCommerce | Price List-based, rate-limited API calls |
| **Payment Entries** | Auto-create | From WooCommerce orders, supports multiple payment methods |
| **Customer & Address** | Auto-create | Guest order support, dual-account (B2B/B2C) |
| **Shipment Tracking** | ↔ Bidirectional | Advanced Shipment Tracking WooCommerce plugin support |
| **Webhooks** | ← WooCommerce | Real-time order/product sync via webhook endpoint |
| **Multi-Site** | ✅ | Connect unlimited WooCommerce stores per ERPNext instance |

## Compatibility

| Branch | ERPNext Version | Frappe Version |
|---|---|---|
| `version-14` | v14.x | v14.x |
| `version-15` | v15.x | v15.x |
| `version-16` | v16.x | v16.x |

## Installation

```bash
# On your Frappe Bench
bench get-app https://github.com/codepromaxtech/ErpnextWooCommerceConnector --branch version-15
bench --site your-site.local install-app woocommerce_center
bench --site your-site.local migrate
```

## Migration from Legacy Apps

If migrating from `woocommerce_fusion`, `woocommerce_integration`, or `woocommerce_connector`:

```bash
bench --site your-site.local migrate
```

The migration patch automatically copies:
- WooCommerce Server records
- WooCommerce Integration Settings
- Item ↔ WooCommerce Server links

## Configuration

1. **WooCommerce Server** — Add your WooCommerce store URL, API keys, and configure settings
2. **WooCommerce Integration Settings** — Set global sync dates and minimum creation date
3. **Webhooks** — Configure WooCommerce to send webhooks to `https://your-site.local/api/method/woocommerce_center.woocommerce_endpoint.handle_webhook`

## Architecture

```
woocommerce_center/
├── hooks.py                    # Doc events, scheduler, fixtures, overrides
├── woocommerce_endpoint.py     # Webhook receiver endpoint
├── tasks/
│   ├── sync.py                 # Base synchronisation class
│   ├── sync_items.py           # Item ↔ WooCommerce Product sync
│   ├── sync_sales_orders.py    # Sales Order ↔ WooCommerce Order sync
│   ├── stock_update.py         # ERPNext → WooCommerce stock levels
│   └── sync_item_prices.py     # ERPNext → WooCommerce prices
├── overrides/
│   └── selling/sales_order.py  # Custom autoname + status sync
├── woocommerce/
│   ├── woocommerce_api.py      # WooCommerceResource virtual doctype base
│   └── doctype/                # All DocType definitions
└── patches/                    # Migration patches
```

## License

MIT
