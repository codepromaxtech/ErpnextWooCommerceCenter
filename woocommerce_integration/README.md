# WooCommerce Integration for ERPNext

This repository hosts the integration solution for connecting ERPNext with WooCommerce, allowing for seamless synchronization of data across both platforms.

> [!NOTE]
> For detailed documentation and setup guides please refer to the [Wiki](https://github.com/alyf-de/woocommerce_integration/wiki)
## Features

The integration supports a variety of functionalities to streamline your e-commerce and ERP operations:

- **Sales Order Synchronization**: Automatically pulls sales orders from WooCommerce into ERPNext, including associated customers, contacts, addresses, and items.
- **Item Data Retrieval**: Retrieves missing item data from WooCommerce to ensure all ordered items are present in ERPNext.
- **Stock Level Updates**: Pushes updates on item stock levels from ERPNext back to WooCommerce to maintain accurate inventory data across both systems.
- **Configurable Synchronization Intervals**: Allows customization of the frequency at which data synchronization occurs, enabling you to optimize performance based on your operational needs.

## Getting Started

Install on a self-hosted ERPNext instance:

```bash
bench get-app https://github.com/alyf-de/woocommerce_integration --branch version-14
bench --site $SITE_NAME install-app woocommerce_integration
```

## License

GPLv3

## Support

For bug reports, please file an issue on this GitHub repository. For paid support and feature requests, please reach out to hallo@alyf.de.
