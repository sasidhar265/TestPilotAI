# Quotation Services supported catalogue

Use these canonical BRD v1.0 values exactly. Membership does not prove a specific brand/product/
customer/vehicle/term/maintenance combination is eligible; eligibility remains configured.

## Brands

| Code | Brand |
|---|---|
| `AUDI` | Audi |
| `SKODA` | Škoda |
| `SEAT` | SEAT |
| `CUPRA` | CUPRA |
| `VWPC` | Volkswagen Passenger Cars |
| `VWCV` | Volkswagen Commercial Vehicles |
| `TATA` | Tata |
| `MAHINDRA` | Mahindra |
| `TOYOTA` | Toyota |
| `PORSCHE` | Porsche |
| `BENTLEY` | Bentley |

Do not add Lamborghini or undefined aliases. Unknown/inactive brands use `INVALID_BRAND`;
configured brand/product failures use `PRODUCT_NOT_AVAILABLE_FOR_BRAND`.

## Products

| Code | Product | Distinguishing behavior |
|---|---|---|
| `PCP` | Personal Contract Purchase | Instalments plus GFV/optional final payment |
| `HP` | Hire Purchase | Normally amortizing finance without a large GFV |
| `LP` | Lease Purchase | Instalments accounting for balloon/final payment |
| `PCH` | Personal Contract Hire | Rentals, mileage, maintenance and VAT |
| `BCH` | Business Contract Hire | Rental net, VAT and gross values |
| `PFL` | Personal Finance Lease | Approved PFL definition; final rental if applicable |
| `BFL` | Business Finance Lease | Net, VAT and gross values where required |

Do not generate Conditional Sale. Do not transfer PCP/HP calculations or regulatory classification
to another code without an approved rule. Use `INVALID_PRODUCT` for unsupported/inactive codes and
`PRODUCT_NOT_AVAILABLE_FOR_CUSTOMER` for configured customer ineligibility.

## Maintenance and APR

Maintenance codes are `S`, `SM`, and `SMT`. Their contents, eligibility, pricing and VAT are
configuration-driven. Do not invent labels or prices. Use `INVALID_MAINTENANCE_OPTION` or
`MAINTENANCE_RATE_NOT_AVAILABLE` as applicable.

The BRD defines applicable individual UK APR and separately configured representative APR; it does
not define targeted/non-targeted solver modes. Never generate `aprMode` or target-APR solver
requirements unless newer source explicitly introduces them. Exact APR needs an approved UK
reference example or approved independent calculator.

## Coverage policy

For full-catalogue requests, cover every listed value at least once with readable Scenario Outlines
or risk-based pairwise rows where behavior is shared. Separate cases when calculation, audience,
VAT, disclosure, oracle or error differs. Avoid the full Cartesian product unless explicitly
required or an approved eligibility matrix makes every combination material.
