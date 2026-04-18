# Changelog

All notable changes to **WooCommerce Center** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-04-18

### Added

#### Product / Item Sync
- Bidirectional Item ↔ WooCommerce Product synchronisation
- Hash-based change detection to prevent sync loops
- JSONPath-based custom field mapping
- Variant and attribute support (accumulate values, don't replace)
- Image sync (featured + gallery images)
- Flexible item code naming (WooCommerce ID / SKU / Naming Series)
- Weight unit conversion (g, kg, lb, lbs, oz)
- UOM auto-creation from SKU
- Hourly scheduler sync + webhook-triggered real-time sync

#### Sales Order Sync
- Bidirectional Sales Order ↔ WooCommerce Order synchronisation
- Customer & address auto-creation with guest order support
- B2B dual account support
- Tax line sync (template-based or actual amounts)
- Shipping charge sync with shipping rule mapping
- Fee line sync (WooCommerce order fees)
- Payment Entry auto-creation with multi-payment method bank account mapping
- Sales Invoice auto-creation (optional)
- Customer note preservation
- Custom autoname for WooCommerce-linked Sales Orders
- Bidirectional order status mapping (ERPNext ↔ WooCommerce)
- Order cancellation via webhook

#### Stock Sync
- ERPNext → WooCommerce stock level push
- Multi-warehouse stock summation
- Product variant support (parent/variation endpoints)
- Reserved stock subtraction (configurable)
- Triggered on Stock Entry, Sales Invoice, Delivery Note, Stock Reconciliation
- Daily full sync scheduler

#### Price Sync
- ERPNext Item Price → WooCommerce regular_price sync
- Price List-based sync per WooCommerce Server
- Triggered on Item Price update + daily scheduler
- Rate-limited API calls (configurable delay)

#### Webhooks
- HMAC-SHA256 verified webhook endpoints
- order.created, order.updated, order.deleted handlers
- product.updated handler
- Multi-server webhook routing (auto-detects matching server)

#### Multi-Site
- Multiple WooCommerce Server support (unlimited stores)
- Per-server configuration for all sync features
- Server auto-named from domain URL

#### Infrastructure
- `WooCommerce Server` doctype — consolidated per-store config
- `WooCommerce Integration Settings` — global sync timestamps
- `WooCommerce Order` — virtual doc (live WC orders)
- `WooCommerce Product` — virtual doc (live WC products)
- `WooCommerce Request Log` — HTTP request/response audit trail with auto-cleanup
- `Item WooCommerce Server` — child table linking Items to WC stores
- 5 child tables: Warehouse, Item Field Map, Order Item Field Map, Shipping Rule, Order Status
- API request logging wrapper (`APIWithRequestLogging`)
- Conflicting app detection on install
- Migration patch from legacy apps (woocommerce_fusion, woocommerce_integration, woocommerce_connector)
- Frappe Workspace with shortcuts
- ERPNext v14, v15, and v16 support (separate branches)

### Migration

- `patches/v1/migrate_from_legacy_apps.py` — idempotent migration from:
  - `woocommerce_fusion` → WooCommerce Server, Integration Settings, Item links
  - `woocommerce_integration` → Integration Settings
  - `woocommerceconnector` → Item links, Customer identifiers
