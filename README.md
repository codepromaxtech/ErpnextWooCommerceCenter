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

### Step 1 — Install the App

```bash
# Pick the branch matching your ERPNext version
bench get-app https://github.com/codepromaxtech/ErpnextWooCommerceCenter --branch version-15

# Install on your site
bench --site your-site.local install-app woocommerce_center

# Apply database migrations
bench --site your-site.local migrate

# Restart & rebuild assets
bench restart
bench --site your-site.local clear-cache
```

### Step 2 — Generate WooCommerce API Keys

1. In your **WooCommerce** store, go to **WooCommerce → Settings → Advanced → REST API**
2. Click **Add Key**
3. Set **Description** to `ERPNext`, **User** to your admin, **Permissions** to `Read/Write`
4. Click **Generate API Key**
5. Copy the **Consumer Key** and **Consumer Secret** — you'll need them in Step 3

### Step 3 — Create a WooCommerce Server

1. In ERPNext, navigate to **WooCommerce Server → + Add WooCommerce Server**
2. Fill in:

| Field | Value |
|---|---|
| **WooCommerce Server URL** | `https://your-shop.com` (no trailing slash) |
| **API Consumer Key** | Paste from Step 2 |
| **API Consumer Secret** | Paste from Step 2 |
| **Enable Sync** | ✅ Check to activate |
| **Company** | Your ERPNext company |
| **Warehouse** | Default warehouse for incoming orders |

3. Click **Save** — the document will auto-name itself from the domain

### Step 4 — Set Global Sync Settings

1. Navigate to **WooCommerce Integration Settings**
2. Set **Last Synchronisation Date** to the date you want to start pulling orders from (e.g. `2024-01-01`)
3. Optionally set **Minimum Creation Date** to ignore very old orders
4. Set **Naming Series** for auto-created Sales Orders (e.g. `SO-WOO-.#####`)
5. Click **Save**

---

## 📦 Product / Item Sync

Products sync **bidirectionally** — WooCommerce ↔ ERPNext.

### Automatic Sync

| Trigger | Direction | When |
|---|---|---|
| **Hourly scheduler** | WC → ERPNext | Every hour, pulls all products modified since last sync |
| **Item saved/created in ERPNext** | ERPNext → WC | Immediately on save (if item is linked to a WC server) |
| **Webhook** (`product.updated`) | WC → ERPNext | Real-time (requires webhook setup, see below) |

### Manual Sync — From WooCommerce to ERPNext

1. Navigate to **WooCommerce Product** list
2. Open any product — it shows the **live** data from WooCommerce (virtual document)
3. Click **Actions → Sync this Item to ERPNext**
4. The product will be created/updated as an ERPNext **Item**

### Manual Sync — From ERPNext to WooCommerce

1. Open any **Item** in ERPNext
2. Go to the **WooCommerce** tab
3. Click **Sync this Item with WooCommerce** button on the toolbar

### Field Mapping (Advanced)

In your **WooCommerce Server**, go to the **Item Field Map** section to map custom ERPNext Item fields to WooCommerce product fields using **JSONPath** expressions.

Example mappings:

| ERPNext Field | WooCommerce JSONPath | Purpose |
|---|---|---|
| `custom_weight` | `$.weight` | Sync weight |
| `custom_barcode` | `$.sku` | Sync SKU/barcode |
| `description` | `$.short_description` | Sync short description |

### Image Sync

Enable **Enable Image Sync** on the WooCommerce Server to sync product images. WooCommerce product images will be downloaded and attached to ERPNext Items, and vice versa.

---

## 📊 Stock Level Sync

Stock syncs from **ERPNext → WooCommerce** (one-way).

### Automatic Sync

| Trigger | When |
|---|---|
| **Stock Entry** submitted/cancelled | Immediately |
| **Sales Invoice** submitted/cancelled | Immediately |
| **Delivery Note** submitted/cancelled | Immediately |
| **Stock Reconciliation** submitted/cancelled | Immediately |
| **Daily scheduler** | Once a day — full sync of all enabled items |

### Manual Sync

1. Open any **Item** in ERPNext
2. Click **Sync this Item's Stock Levels to WooCommerce** on the toolbar
3. Stock levels are pushed to all linked WooCommerce servers

### Multi-Warehouse

In your **WooCommerce Server**, add multiple warehouses in the **Warehouses** child table. The app will calculate total stock across all listed warehouses.

### Reserved Stock

Enable **Subtract Reserved Stock** on the WooCommerce Server to deduct reserved quantities from the available stock sent to WooCommerce. This requires ERPNext's **Stock Reservation** feature to be enabled in Stock Settings.

---

## 🛒 Sales Order Sync

Orders sync **bidirectionally** — WooCommerce ↔ ERPNext.

### Automatic Sync

| Trigger | Direction | When |
|---|---|---|
| **Hourly scheduler** | WC → ERPNext | Every hour, pulls orders modified since last sync date |
| **Webhook** (`order.created` / `order.updated`) | WC → ERPNext | Real-time (requires webhook setup) |
| **Sales Order submitted in ERPNext** | ERPNext → WC | Immediately syncs status back to WooCommerce |

### What Gets Synced

When a WooCommerce order is synced to ERPNext, the app automatically:

1. **Creates or finds the Customer** — matched by email or guest identifier
2. **Creates or updates Billing & Shipping Addresses**
3. **Creates a Contact** — linked to the customer
4. **Creates missing Items** — any products in the order not yet in ERPNext
5. **Creates the Sales Order** with:
   - All line items with correct quantities and prices
   - Tax lines (template-based or actual amounts)
   - Shipping charges and shipping rules
   - Fee lines (e.g. WooCommerce order fees)
   - Customer notes
   - WooCommerce payment method
6. **Optionally auto-submits** the Sales Order (configurable per server)
7. **Creates a Payment Entry** if payment method mapping is configured

### Manual Sync — From WooCommerce to ERPNext

1. Navigate to **WooCommerce Order** list
2. Open any order — shows **live** WooCommerce data (virtual document)
3. Click **Actions → Sync this Order to ERPNext**

### Manual Sync — From ERPNext to WooCommerce

1. Open any **Sales Order** in ERPNext that has a WooCommerce ID
2. Click **Sync this Order with WooCommerce** on the toolbar
3. Status changes and line item updates will push back to WooCommerce

### Order Status Mapping

In your **WooCommerce Server**, go to the **Sales Order Status Map** section to map ERPNext Sales Order statuses to WooCommerce order statuses.

Default mapping:

| ERPNext Status | WooCommerce Status |
|---|---|
| Pending Payment | `pending` |
| Processing | `processing` |
| On hold | `on-hold` |
| Shipped | `completed` |
| Cancelled | `cancelled` |
| Refunded | `refunded` |

### Payment Entry Auto-Creation

1. In **WooCommerce Server**, enable **Enable Payments Sync**
2. Configure the **Payment Method → Bank Account Mapping** (JSON format):
   ```json
   {
     "stripe": "Bank Account - Company",
     "paypal": "PayPal Account - Company",
     "cod": "Cash - Company"
   }
   ```
3. Configure the **Payment Method → GL Account Mapping** similarly
4. When a paid WooCommerce order syncs, a Payment Entry is auto-created

---

## 💰 Price Sync

Prices sync from **ERPNext → WooCommerce** (one-way).

### Automatic Sync

| Trigger | When |
|---|---|
| **Item Price saved** in ERPNext | Immediately pushes to WooCommerce |
| **Daily scheduler** | Once a day — full sync of all enabled item prices |

### Manual Sync

1. Open any **Item** in ERPNext
2. Click **Sync this Item's Price to WooCommerce** on the toolbar

---

## 🔔 Webhook Setup (Real-time Sync)

Webhooks enable **instant** sync instead of waiting for the hourly scheduler.

### Step 1 — Get Your Secret

1. Open your **WooCommerce Server** in ERPNext
2. Copy the value from the **Secret** field (auto-generated on save)

### Step 2 — Create Webhooks in WooCommerce

In your WooCommerce store → **Settings → Advanced → Webhooks**, create these:

| # | Name | Topic | Delivery URL | Secret |
|---|---|---|---|---|
| 1 | Order Created | `Order created` | `https://your-erp-site.com/api/method/woocommerce_center.woocommerce_endpoint.create_order` | Paste secret |
| 2 | Order Updated | `Order updated` | `https://your-erp-site.com/api/method/woocommerce_center.woocommerce_endpoint.update_order` | Paste secret |
| 3 | Order Deleted | `Order deleted` | `https://your-erp-site.com/api/method/woocommerce_center.woocommerce_endpoint.delete_order` | Paste secret |
| 4 | Product Updated | `Product updated` | `https://your-erp-site.com/api/method/woocommerce_center.woocommerce_endpoint.update_product` | Paste secret |

> **Important:** Set **API Version** to `WP REST API Integration v3` for all webhooks.

### Step 3 — Verify

1. Place a test order on your WooCommerce store
2. Check ERPNext → **Sales Order** list — a new order should appear within seconds
3. If it doesn't, check **Error Log** in ERPNext for webhook errors

### Security

All webhooks are verified using **HMAC-SHA256** signature validation. Each incoming request is matched against your server's secret to prevent unauthorized access.

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
│   └── doctype/                    # 11 DocType definitions
│
├── public/js/                      # Client-side form enhancements
├── patches/                        # Migration patches
├── translations/                   # i18n (German included)
└── config/                         # Desk module config
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
