<p align="center">
  <img src="woocommerce_center/public/images/woocommerce_center_logo.svg" alt="WooCommerce Center" width="128" height="128">
</p>

<h1 align="center">WooCommerce Center</h1>

<p align="center">
  <strong>All-in-one WooCommerce ↔ ERPNext Connector</strong><br>
  Multi-site, bidirectional synchronisation of orders, products, stock, prices, payments &amp; webhooks.
</p>

<p align="center">
  <a href="#installation"><img src="https://img.shields.io/badge/ERPNext-v14_|_v15_|_v16-blue?style=flat-square" alt="ERPNext"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
  <a href="https://github.com/codepromaxtech/ErpnextWooCommerceCenter"><img src="https://img.shields.io/badge/maintainer-CodeProMax_Tech-purple?style=flat-square" alt="Maintainer"></a>
</p>

---

## ✨ Features

| Feature | Direction | Details |
|---|---|---|
| **Product / Item Sync** | ↔ Bidirectional | Create, update, field mapping via JSONPath, variant & attribute support, image sync |
| **Sales Order Sync** | ↔ Bidirectional | Hash-based change detection, status mapping, auto-naming, fee lines |
| **Stock Level Sync** | → WooCommerce | Multi-warehouse, variant support, reserved stock subtraction |
| **Item Price Sync** | → WooCommerce | Price-list based, rate-limited API calls |
| **Payment Entries** | Auto-create | From WooCommerce orders, supports multiple payment gateways with bank account mapping |
| **Customer & Address** | Auto-create | Guest order support, dual-account (B2B / B2C), VAT ID capture |
| **Shipment Tracking** | ↔ Bidirectional | WooCommerce Advanced Shipment Tracking plugin support |
| **Shipping Rules** | ← WooCommerce | Map WooCommerce shipping methods to ERPNext Shipping Rules |
| **Tax Sync** | ← WooCommerce | Template-based or actual-amount tax lines, per-item + shipping tax |
| **Webhooks** | ← Real-time | Secure HMAC-SHA256 verified endpoints for orders & products |
| **Multi-Site** | ✅ Unlimited | Connect multiple WooCommerce stores per ERPNext instance |

---

## 🔗 Compatibility

| Branch | ERPNext | Frappe | Python |
|---|---|---|---|
| [`version-14`](https://github.com/codepromaxtech/ErpnextWooCommerceCenter/tree/version-14) | v14.x | v14.x | 3.10+ |
| [`version-15`](https://github.com/codepromaxtech/ErpnextWooCommerceCenter/tree/version-15) | v15.x | v15.x | 3.11+ |
| [`version-16`](https://github.com/codepromaxtech/ErpnextWooCommerceCenter/tree/version-16) | v16.x | v16.x | 3.12+ |

---

## 🚀 Installation

```bash
# Replace --branch with your ERPNext version
bench get-app https://github.com/codepromaxtech/ErpnextWooCommerceCenter --branch version-15
bench --site your-site.local install-app woocommerce_center
bench --site your-site.local migrate
```

### Dependencies

The app installs these Python packages automatically via `pyproject.toml`:

- [`woocommerce`](https://pypi.org/project/WooCommerce/) — WooCommerce REST API client
- [`jsonpath-ng`](https://pypi.org/project/jsonpath-ng/) — JSONPath field mapping

---

## 🔄 Migrating from Legacy Apps

If you are migrating from **woocommerce_fusion**, **woocommerce_integration**, or **woocommerce_connector**:

```bash
bench --site your-site.local install-app woocommerce_center
bench --site your-site.local migrate
```

The migration patch (`v1/migrate_from_legacy_apps.py`) automatically transfers:

- ✅ WooCommerce Server records & settings
- ✅ WooCommerce Integration Settings (sync dates, naming series)
- ✅ Item ↔ WooCommerce Server links (product IDs, servers)
- ✅ Custom fields on Customer, Address, Sales Order, Contact, Item

> **Note:** After migrating, you can safely uninstall the legacy app. WooCommerce Center will warn you if a conflicting app is still installed.

---

## ⚙️ Configuration

### 1. WooCommerce Server

Navigate to **WooCommerce Server** and create a new record:

- **Server URL** — Your WooCommerce store URL (e.g. `https://shop.example.com`)
- **API Keys** — Consumer Key & Secret from WooCommerce → Settings → REST API
- **Sync Settings** — Enable/disable order sync, stock sync, price sync, item sync
- **Warehouse** — Default ERPNext warehouse for stock
- **Company** — ERPNext company for Sales Orders
- **Tax Configuration** — Tax template or actual tax mode
- **Payment Mapping** — Map WooCommerce payment methods to bank accounts

### 2. WooCommerce Integration Settings

Set global settings:

- **Last Sync Date** — Controls which orders to pull during batch sync
- **Minimum Creation Date** — Ignore orders older than this date

### 3. Webhooks (Real-time Sync)

In your WooCommerce store → Settings → Advanced → Webhooks, create:

| Topic | Delivery URL |
|---|---|
| Order created | `https://your-site/api/method/woocommerce_center.woocommerce_endpoint.create_order` |
| Order updated | `https://your-site/api/method/woocommerce_center.woocommerce_endpoint.update_order` |
| Order deleted | `https://your-site/api/method/woocommerce_center.woocommerce_endpoint.delete_order` |
| Product updated | `https://your-site/api/method/woocommerce_center.woocommerce_endpoint.update_product` |

- **Secret** — Copy from your WooCommerce Server document's `Secret` field
- **API Version** — WP REST API Integration v3

---

## 🏗️ Architecture

```
woocommerce_center/
├── hooks.py                        # Doc events, scheduler, fixtures, overrides
├── install.py                      # Custom fields, default records
├── exceptions.py                   # Custom exception classes
├── utils.py                        # Tax, UOM, country helpers
├── woocommerce_endpoint.py         # HMAC-verified webhook receivers
│
├── tasks/
│   ├── sync.py                     # Base SynchroniseWooCommerce class
│   ├── sync_items.py               # Item ↔ WooCommerce Product sync
│   ├── sync_sales_orders.py        # Sales Order ↔ WooCommerce Order sync
│   ├── stock_update.py             # ERPNext → WooCommerce stock levels
│   ├── sync_item_prices.py         # ERPNext → WooCommerce prices
│   └── utils.py                    # API request logging wrapper
│
├── overrides/
│   └── selling/sales_order.py      # Custom autoname + submit/cancel hooks
│
├── woocommerce/
│   ├── woocommerce_api.py          # WooCommerceResource virtual doctype base
│   └── doctype/
│       ├── woocommerce_server/     # Multi-site server config (main settings)
│       ├── woocommerce_order/      # Virtual doctype — live WC orders
│       ├── woocommerce_product/    # Virtual doctype — live WC products
│       ├── woocommerce_request_log/# API request audit log
│       ├── woocommerce_integration_settings/  # Global sync settings
│       ├── item_woocommerce_server/           # Child: per-item WC links
│       ├── woocommerce_server_item_field/     # Child: JSONPath field map
│       ├── woocommerce_server_order_item_field/ # Child: SO→WC field map
│       ├── woocommerce_server_order_status/   # Child: status mapping
│       ├── woocommerce_server_shipping_rule/  # Child: shipping rule map
│       └── woocommerce_server_warehouse/      # Child: warehouse list
│
├── public/js/
│   ├── selling/sales_order.js      # SO form: sync buttons, WC actions
│   ├── selling/sales_order_list.js # SO list: WC indicator column
│   └── stock/item.js               # Item form: stock/price sync buttons
│
├── patches/
│   └── v1/migrate_from_legacy_apps.py  # One-time migration from legacy apps
│
├── translations/
│   └── de.csv                      # German translations
│
└── config/
    ├── desktop.py                  # Module desk icon
    └── docs.py                     # Documentation context
```

---

## 📂 Doctypes

| DocType | Type | Purpose |
|---|---|---|
| **WooCommerce Server** | Document | Per-store connection config, API keys, sync rules |
| **WooCommerce Integration Settings** | Single | Global sync dates, naming series |
| **WooCommerce Order** | Virtual | Browse & sync live WooCommerce orders |
| **WooCommerce Product** | Virtual | Browse & sync live WooCommerce products |
| **WooCommerce Request Log** | Document | API call audit trail |
| **Item WooCommerce Server** | Child Table | Links an ERPNext Item to a WC store |
| 5× Server child tables | Child Table | Field maps, status maps, shipping rules, warehouses |

---

## 🧑‍💻 Developer

**CodeProMax Tech** — Md. Al-Amin  
📧 codepromaxtech@gmail.com  
🔗 [GitHub](https://github.com/codepromaxtech)

Built upon and extends the excellent work of:
- [woocommerce_fusion](https://github.com/dvdl16/woocommerce_fusion) by Dirk van der Laarse (Starktail)
- [woocommerce_integration](https://github.com/alyf-de/woocommerce_integration) by ALYF GmbH

---

## 📄 License

[MIT](LICENSE)
