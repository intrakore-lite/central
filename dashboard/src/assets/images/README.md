# Image logos

The Frappe offering, keyed `pilot`, uses the brand logo from `src/lib/brand.ts`.

Ubuntu uses the official [Circle of Friends artwork](https://assets.ubuntu.com/v1/ce518a18-CoF-2022_solid+O.svg).

Apps uses `apps.svg`, drawn for Central: a rounded square with a grid of app tiles.

Image Offering uploads override these bundled defaults.
Apps without a logo in their template use `apps.svg`. An app's own logo comes from its `template.yaml` through Cargo.
