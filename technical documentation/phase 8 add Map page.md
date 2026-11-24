# Shipment and Entity Map: Technical Summary

**Project:** Admin Risk Dashboard (Saudi payment platform, prototype)
**Status:** Data check, coordinates, API endpoints, and map page written. Verification partly complete (see section 8).
**Data:** Synthetic only

---

## 1. Purpose

The admin needs to see where customers, stores, and shipments are, and how fraud and default bands are distributed geographically. The map shows city-level positions only, with shipment flows between cities.

---

## 2. Scope decisions

| Decision | Reason |
|---|---|
| City-level points, not street addresses | Customer addresses are personal data under PDPL. City level is the safer choice, even for synthetic data. |
| Each point placed near its city center with a small offset | Points in the same city would otherwise stack on one spot. |
| Offset derived from a hash of the entity key | The same entity lands in the same place on every run, with no stored state. |
| Plotly `scattermap` for the map | Plotly was already a project dependency, so no new library was added. |
| Fraud band colors by default, with a switch to default band | Fraud is the primary admin concern. Both are available without a second page. |
| Shipment flows drawn as lines, same-city shipments as counts | Lines between identical cities are invisible, so those are shown in a table. |
| Store points shown as unscored | Store scores are not built yet. Showing them as gray avoids implying a value. |

---

## 3. Data check

A read-only script confirmed the location fields in the database.

| Table | Field | Values | Missing |
|---|---|---|---|
| `customers` | `city` | 6 Saudi cities | 0 of 10,000 |
| `stores` | `city` | 6 Saudi cities | 0 of 500 |
| `shipments` | `origin_city`, `destination_city` | 6 Saudi cities | 0 of 80,380 |

No latitude, longitude, street address, or postal code exists in the schema. Deals, transactions, and payment events have no location fields.

A second read-only check joined shipments to deals, customers, and stores:

| Check | Result |
|---|---|
| Shipments with no deal, customer, or store | 0 |
| `origin_city` equals store `city` | 80,380 of 80,380 (100%) |
| `destination_city` equals customer `city` | 80,380 of 80,380 (100%) |

The shipment fields are copies of the store and customer cities, so no correction is needed.

---

## 4. Components

| File | Change | Purpose |
|---|---|---|
| `app/geo.py` | New | City center coordinates and deterministic offset function |
| `app/api/routers/map_data.py` | New | Two read-only endpoints: `/map/points` and `/map/shipment-flows` |
| `app/api/main.py` | Edited | Registers the map router |
| `dashboard/pages/4_Map.py` | New | Streamlit map page |
| `dashboard/api_client.py` | Unchanged | Reused for all API calls |
| `dashboard/config.py` | Unchanged | Supplies `BAND_COLORS` and API settings |

---

## 5. Coordinate module (`app/geo.py`)

- `CITY_CENTERS` maps each of the six cities to approximate center coordinates (latitude, longitude).
- `city_point(city, key)` returns a point near the center.
- The offset comes from the SHA-256 digest of the key (for example `customer:123`). The first 4 bytes give the x offset and the next 4 give the y offset. Each is scaled to the range -1 to 1, then multiplied by `MAX_OFFSET_DEG = 0.015`, about 1.5 km at this latitude.
- The same key always gives the same point. Entities in the same city are spread out.
- A self-check (`python -m app.geo`) confirms determinism and that offsets stay within the limit. It passed for all six cities.

---

## 6. API endpoints (`app/api/routers/map_data.py`)

All routes use the existing API key dependency from the application.

### 6.1 `GET /map/points?entity=customer|store`

- **Customers:** reads `id` and `city` from `customers`, and the latest `risk_scores` row per customer (highest `id` per `entity_id`, filtered by `entity_type = "customer"`).
- **Stores:** reads `id` and `city` from `stores`. No scores are loaded, so bands are `null`.
- Returns one object per entity: `entity_type`, `entity_id`, `city`, `lat`, `lon`, `fraud_band`, `default_band`, `model_version`.
- Coordinates are rounded to six decimals.
- No names, phone numbers, or ground-truth fields are returned.

### 6.2 `GET /map/shipment-flows`

Groups shipments by `(origin_city, destination_city)` and computes:

| Field | Definition |
|---|---|
| `shipments` | Count of shipments in the pair |
| `delivered` | Shipments with `final_status = "delivered"` |
| `first_attempt_success` | Delivered and `attempts = 1` |
| `not_delivered` | Shipments with any other final status |
| `first_attempt_success_rate` | `first_attempt_success / shipments`, rounded to 4 decimals |

Pairs where origin equals destination go into `same_city`. Other pairs go into `flows`, sorted by shipment count. The response also includes:

- `total_shipments`: sum across all pairs
- `city_centers`: the `CITY_CENTERS` dictionary, so the dashboard can place line endpoints without duplicating coordinates

Shipment data is aggregated in SQL with `GROUP BY`, so the endpoint returns about 36 rows rather than 80,380.

---

## 7. Map page (`dashboard/pages/4_Map.py`)

| Element | Behavior |
|---|---|
| Entity selector | Customers or stores |
| Color selector | Fraud band (default) or default band |
| Shipment line toggle | Off by default. When on, draws one line per origin-destination pair, width scaled from 1 to 7 by shipment count |
| Points | One trace per band (high, medium, low, unscored), colored with `BAND_COLORS`. Legend shows counts |
| Hover text | City, fraud band, and default band only |
| Store notice | Shown when stores are selected |
| Placeholder warning | Shown when any model version starts with `placeholder` |
| Same-city table | Per city: shipments, delivered, first-attempt success rate |
| Caching | `st.cache_data` with a 300-second TTL on both data calls |
| Errors | `ApiError` messages are shown with `st.error` and the page stops |

Map tiles come from OpenStreetMap, which the viewer's browser loads directly.

---

## 8. Verification status

| Check | Result |
|---|---|
| Location fields present and complete | Passed |
| Shipment cities match store and customer cities | Passed (80,380 of 80,380) |
| `python -m app.geo` self-check | Passed (6 cities) |
| `/map/points?entity=customer` returns 10,000 | Passed |
| `/map/shipment-flows` returns total 80,380 | Passed |
| Same request without `X-API-Key` returns 401 | **Not yet reported** |
| `/map/shipment-flows` exposes `city_centers` | **Not yet confirmed** |
| Map page renders in Streamlit | **Not yet reported** |
| Plotly version 5.24 or newer (for `scattermap`) | **Not yet checked** |

---

## 9. Known limits

1. **City-level only.** The map shows where a customer or store is in general, not where they live or operate.
2. **Offset is cosmetic.** The 1.5 km spread separates points within a city. It does not reflect real locations.
3. **Approximate geography.** City coordinates are approximate, and shipment routes are drawn as straight lines, not roads.
4. **Store scores not built.** All store points show as unscored, so the store view carries no risk information.
5. **Scores are placeholders or early outputs.** The warning appears if the model version starts with `placeholder`. Current customer scores come from the default model and the fraud rules, which are not yet validated on real data.
6. **Shipment flows are counts.** The map shows volume and first-attempt success, not causes. A high failure rate on a route may come from the generator's rules, not real logistics.
7. **Same-city shipments are not drawn.** They appear only in the table.
8. **Map tiles depend on the internet.** The viewer's browser must reach OpenStreetMap.
9. **No automated tests for the map page.** The endpoints can be tested, but the page is checked by hand.
10. **API key scope not confirmed.** The design assumes the API key check covers the new routes, but this has not been verified by the 401 test.

---

## 10. Open items

- [ ] Run the no-key request and confirm it returns 401.
- [ ] Confirm `city_centers` appears in the shipment-flows response.
- [ ] Check the Plotly version (5.24 or newer).
- [ ] Open the Map page and check each control (entity, color, shipment lines, same-city table).
- [ ] Confirm the import style in `4_Map.py` matches the other pages.
- [ ] Check whether other pages call `st.set_page_config`, and match it.
- [ ] If Streamlit warns about `use_container_width`, switch to the newer `width` argument.
- [ ] Add the map to the demo script, with the limits in section 9 stated.
- [ ] Add endpoint tests for `/map/points` and `/map/shipment-flows` to the API test suite.