---
paths:
  - "src/esl/square/**/*.py"
  - "src/esl/catalog/**/*.py"
  - "tests/**/*square*.py"
---

# Square SDK

The installed package is `squareup>=44,<45`. It installs as `squareup` and
imports as `square`.

Version 42 was a full rewrite with breaking changes to client construction
and parameter names. Most training data and nearly every tutorial online
describes the legacy client. Assume any remembered API shape is wrong.

## Verify before writing

Check the real surface rather than recalling it:

```
python -c "from square import Square; print([a for a in dir(Square(token='x').catalog) if not a.startswith('_')])"
```

Known corrections:

- `catalog.search()` — NOT `catalog.search_objects()`
- `catalog.list()` returns a `SyncPager`, which auto-paginates
- Variations expose `upc`, not `barcode`
- `location_overrides` carries per-location pricing and overrides the
  top-level `price_money` at the register

## Client construction

```python
Square(
    environment=SquareEnvironment.SANDBOX,  # defaults to PRODUCTION if omitted
    token=...,
    version="2026-05-20",                   # matches the 44.1.0.20260520 build
)
```

Always pass `environment` explicitly. The default is production.

Always pin `version`. Unpinned, it floats to latest and a package upgrade
silently changes response shapes.

## Do not

- Import `square_legacy` or use `Client(access_token=...)`.
- Call any write endpoint: `upsert`, `batch_upsert`, `batch_delete`,
  `update_item_taxes`, `update_item_modifier_lists`. This service is
  read-only. If a task seems to require a write, stop and ask.
- Hit the live sandbox in tests. Use recorded fixtures.

## Field handling

`price_money` is None when `pricing_type == "VARIABLE_PRICING"`.
`sku` is frequently empty. `track_inventory` defaults to false.
Handle all three explicitly; do not assume presence.