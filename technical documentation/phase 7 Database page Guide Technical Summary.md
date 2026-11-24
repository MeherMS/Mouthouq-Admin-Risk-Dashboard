# Database Guide: Technical Summary

**Project:** Admin Risk Dashboard (Saudi payment platform, prototype)
**Addition:** Read-only Database Guide page and its API endpoint
**Status:** Code written. Not yet run locally, tested, or deployed. Several names are assumed and need confirmation (section 9).
**Data:** All synthetic.

---

## 1. Purpose

Non-technical team members need a way to understand what the database holds without reading schema files or SQL. This addition provides one dashboard page that shows:

- What each table is for, in plain language
- How the tables connect
- Row counts and headline numbers
- Simple category counts (for example, deals by status)
- Recommendations and a glossary

The page is read-only and describes the structure of the data. It does not show individual customers, stores, or transactions.

---

## 2. Constraints

| Constraint | How it was handled |
|---|---|
| Do not change existing code | New files only. The only change to existing code is two lines in `app/api/main.py` to register the router |
| Dashboard reads through the API only (Phase 4 rule) | The page calls one new endpoint. It has no database access |
| Protected endpoints require the API key (Phase 6) | The new router follows the same key rule. This is an assumption until confirmed (section 9) |
| No personal identifiers | The endpoint returns no names, phones, emails, or national ID hashes, and no row-level data |
| Synthetic-only fields must not leak (Phase 1 and 3 rules) | Their names appear in the schema view, labeled as generator-only. Their values and statistics are never returned |

---

## 3. Architecture of the addition

```
Dashboard page (Streamlit)              API (FastAPI)
dashboard/pages/4_Database.py  ──GET──▶  /database/overview
        │                                       │
        │  reads JSON                           │  SQLAlchemy inspector
        ▼                                       │  + hand-written notes
   tables, diagram,                             ▼
   statistics, glossary                    SQLite / PostgreSQL
                                           (metadata and aggregate counts only)
```

The endpoint does most of the work. The page only renders what it receives. This keeps logic in one place, and the page stays simple to read.

---

## 4. Components

| Component | File | Role |
|---|---|---|
| Overview router | `app/api/routers/database_overview.py` (new) | Builds the overview JSON |
| Router registration | `app/api/main.py` (two lines added) | Mounts the router |
| Dashboard page | `dashboard/pages/4_Database.py` (new) | Renders the guide |

---

## 5. API endpoint: `GET /database/overview`

### 5.1 Where the data comes from

| Part of the response | Source |
|---|---|
| Table names, columns, column types, primary keys | SQLAlchemy `inspect()`, read from the live database |
| Foreign-key relations | SQLAlchemy `get_foreign_keys()`, read from the live database |
| Row counts | `SELECT COUNT(*)` per table |
| Table purposes | `TABLE_NOTES` dictionary, written by hand in the router |
| Column meanings | `COLUMN_NOTES` dictionary, written by hand in the router |
| Soft links (conventions the database does not enforce) | `SOFT_LINKS` list, written by hand |
| Category counts | `STAT_SPECS` list, a whitelist of (title, table, column) |
| Headline numbers | `_headline()`, four fixed queries |

The description dictionaries are the main maintenance cost. The schema part updates itself. The descriptions do not.

### 5.2 Synthetic-only handling

`SYNTHETIC_ONLY` lists three fields: `customers.default_label`, `customers.synthetic_profile`, and `deals.is_fraud`.

- Each appears in its table's column list with `synthetic_only: true`.
- Their values are never queried.
- They are excluded from every statistic. `STAT_SPECS` does not reference them.

The field names are visible to anyone with the API key. That is acceptable for the prototype, because the key already grants access to the data, and the page labels the fields. It must be removed before real data is used (Phase 1 known limit 8).

### 5.3 Statistics safety

- Statistics use only columns in `STAT_SPECS`.
- Each entry is skipped if its table or column does not exist. A renamed column therefore produces a missing chart, not an error.
- Identifiers in the SQL come from the database schema and the fixed whitelist, not from user input. The query strings are built with f-strings for this reason. Only identifiers are interpolated; no user values are.
- Results are counts grouped by one column. They return no individual rows.

### 5.4 Response shape

```json
{
  "generated_at": "2026-11-24T10:00:00+00:00",
  "summary":    { "tables": 10, "total_rows": 0, "relationships": 0, "synthetic_only_fields": 3 },
  "tables":     [ { "name", "title", "purpose", "row_count", "columns": [ { "field", "meaning", "type", "key", "synthetic_only" } ] } ],
  "relations":  [ { "from_table", "to_table", "column" } ],
  "soft_links": [ { "from_table", "column", "targets": [] } ],
  "headline":   [ { "label", "value" } ],
  "statistics": [ { "title", "table", "column", "rows": [ { "label", "count" } ] } ]
}
```

`value` in `headline` is a formatted string (for example, `"12.3%"`), so the page displays it without further formatting.

### 5.5 Headline numbers

| Label | Calculation |
|---|---|
| Deals recorded | Total rows in `deals` |
| Share of deals disputed | Disputed deals ÷ all deals |
| Average deal value | Mean of `amount_sar` |
| Deals cover | Earliest and latest `created_at` |

The function returns at most four items. Customers, stores, and failed-payment share are computed but dropped by the `[:4]` slice. This is intentional, but the code should be reviewed if the team wants a different set.

---

## 6. Dashboard page

### 6.1 Section order

1. Title, caption, and an info box stating that all data is synthetic
2. Summary metrics: tables, total rows, links, synthetic-only fields
3. Relationship diagram (Graphviz)
4. One expander per table, with its purpose and a column table
5. Key numbers (headline metrics)
6. Patterns in the data (one table and one bar chart per statistic)
7. Recommendations (hard-coded markdown)
8. Glossary (hard-coded table)

### 6.2 Diagram

- Built as DOT text in `build_dot()`, then rendered with `st.graphviz_chart`.
- Solid arrows: enforced foreign keys from the schema.
- Dashed grey arrows: soft links from `risk_scores.entity_id` and `actions.entity_id`. These can point to customers or stores, so the diagram draws one arrow to each.
- Node labels show the table title and its row count.

### 6.3 Caching and errors

- `load_overview` is cached with `st.cache_data(ttl=600)`, so the API is called at most once every 10 minutes per session setting.
- A `requests` error shows a message and calls `st.stop()`. The rest of the page does not render.
- The API key is read from `st.secrets`, with an environment variable as a fallback.

---

## 7. Technical decisions

| Decision | Reason |
|---|---|
| One endpoint returns everything | One request, one cache entry, simple page code |
| Schema read live from the database | The structure shown always matches the database that is actually running |
| Descriptions kept in code, not the database | No schema change needed; reviewed through Git like other code |
| Statistics limited to a whitelist | Prevents accidental exposure of sensitive or synthetic-only columns |
| Counts only, no rows | Keeps personal data out of the response by design |
| Missing columns skipped, not errors | Protects the page while the schema is still changing |
| Graphviz diagram | Shows the structure at a glance without a custom layout |
| Recommendations and glossary hard-coded | They are guidance, not data, and need human review when they change |

---

## 8. Known limits and risks

1. **Not yet run.** The code has not been executed locally, tested, or deployed. Expect at least one fix after the first run.
2. **Assumed names.** The key dependency, the config variable (`API_BASE_URL`), and the secrets key (`API_KEY`) were taken from earlier phases, not from the actual files. The shipments status column (`final_status`) is also a guess.
3. **Graphviz needs a system package on Streamlit Cloud.** `st.graphviz_chart` requires the `dot` binary. Streamlit Community Cloud does not install it by default. A file named `packages.txt` containing `graphviz` is needed in the repository root. This was not mentioned in the code notes and must be added before deployment.
4. **Description drift.** When a column is added or renamed, the notes in `COLUMN_NOTES` and `TABLE_NOTES` do not update. The page will show "No plain description yet." That message is the warning sign. A test can catch columns with no description (see section 10).
5. **Hard-coded recommendations and glossary.** These will go stale. The page does not read them from anywhere.
6. **Field names exposed to key holders.** Synthetic-only field names are visible through the API. The shared-key model already limits this, but it is a disclosure.
7. **Headline numbers run on every cache miss.** The queries are light for 150,000 deals on SQLite. They have not been timed on the full dataset, and the statistics queries have not been checked on PostgreSQL.
8. **`use_container_width` may be deprecated.** Newer Streamlit versions prefer `width="stretch"`. The code works on older versions and may show warnings on newer ones.
9. **Soft-link targets are fixed.** The diagram assumes `risk_scores` and `actions` point to customers and stores. If another entity type is added, `SOFT_LINKS` must be updated by hand.
10. **No automated tests.** The dashboard has none (consistent with earlier phases). The new endpoint should get API tests (section 10).

---

## 9. Open questions (to confirm before pasting)

1. Is the API key checked globally in `main.py`, or per router? If per router, the dependency name is needed.
2. What are the exact names in `config.py` (`API_BASE_URL`?) and the secrets key (`API_KEY`?)
3. Does `render_sidebar()` already call `st.set_page_config`? If so, the new page should match that pattern.
4. What is the status column name in `shipments`?
5. Should the synthetic-only field names be hidden completely, or kept with the "generator only" label?
6. Is the predictions table from Phase 6 in the database? If yes, its name is needed for the notes.

---

## 10. Testing plan

**Automated (not yet written):**

| Test | Checks |
|---|---|
| No key | `/database/overview` returns 401 |
| Key present | Returns 200 with the expected top-level keys |
| No ground truth | Response contains no values for `default_label`, `synthetic_profile`, or `is_fraud` |
| No personal data | Response contains no `name`, `phone`, `email`, or `national_id_hash` values |
| Counts match | `row_count` for each table equals a direct `COUNT(*)` |
| Descriptions present | Every column has an entry in `COLUMN_NOTES` (catches drift) |

**Manual:**

1. Open `/database/overview` with the key header and check the JSON.
2. Open the Database Guide page in the local dashboard.
3. Check that the diagram renders, and that dashed and solid arrows appear correctly.
4. Log in as a viewer and confirm the page opens.
5. Check the page for any name, phone, email, or ID values.

---

## 11. Maintenance

| When | Action |
|---|---|
| A table is added | Add an entry to `TABLE_NOTES`. Add `STAT_SPECS` entries if useful |
| A column is added | Add an entry to `COLUMN_NOTES` |
| A column is renamed | Update `COLUMN_NOTES` and `STAT_SPECS`. Check the page for missing charts |
| A new entity type is added | Update `SOFT_LINKS` and the recommendations text |
| A synthetic-only field is removed | Remove it from `SYNTHETIC_ONLY` |
| Real data is loaded | Delete `SYNTHETIC_ONLY`, the synthetic-only column markings, and the info box text |

---

## 12. Next steps

1. Answer the questions in section 9.
2. Apply the fixes, run the API locally, and check `/database/overview`.
3. Run the dashboard locally and check the new page.
4. Add `packages.txt` with `graphviz` before pushing.
5. Write the API tests in section 10.
6. Deploy the API to Render first, then the dashboard to Streamlit Cloud.