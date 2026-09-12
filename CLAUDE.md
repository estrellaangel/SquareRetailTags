# ESL Pricing Service

Syncs pricing from Square (read-only) and publishes desired state for
electronic shelf labels. A separate Raspberry Pi gateway, owned by the other
developer, polls this service and drives the tag hardware.

<!-- Detailed Square SDK and frontend rules are path-scoped in .claude/rules/ -->

## Architecture

- Square is the source of truth for price. This service is READ-ONLY against
  the catalog. Never write to Square.
- This service is the source of truth for what each tag displays.
- The gateway is an effector: it renders and pushes, and reports back what it
  displayed. It never originates price data or computes hashes.
- `api/esl-pricing-api.yaml` is the contract with the gateway. Treat it as
  authoritative. Changing an endpoint means changing the spec first.

## Layout

- `src/esl/square/` — the ONLY package permitted to import the Square SDK.
  Everything else works with internal dataclasses.
- `src/esl/catalog/` — sync jobs and the Square mirror.
- `src/esl/tags/` — desired state, content hashing, drift.
- `src/esl/web/` — FastAPI routers. Serves the built frontend in production.
- `frontend/` — Vite + React. See @frontend/README.md

## Rules that are easy to get wrong

- Money is always an integer in the smallest currency unit. 14999 is $149.99.
  Never floats. Never divide before rendering.
- Delta sync cursor: persist the `latest_time` from the previous
  SearchCatalogObjects response and pass it as the next `begin_time`.
  Never `datetime.now()`. `begin_time` is exclusive.
- Diff the projection (name, variation_name, sku, price, pricing_type), not
  the Square `version` field. Square bumps a parent item's version when a
  child variation changes, so version-diffing re-pushes half the fleet.
- Content hashing must be deterministic across processes and restarts:
  sorted keys, integers for money, explicit null handling. Never use Python's
  builtin `hash()`.
- Tag IDs are normalized to 16-char uppercase hex at the API boundary.

## Commands

- `make dev` — uvicorn + vite together
- `make build` — regenerate TS types from the OpenAPI spec, then build
- `pytest` — tests use recorded fixtures in `tests/fixtures/square/`,
  not the live sandbox

## Before saying a change is done

- Run `pytest`.
- If you touched `api/esl-pricing-api.yaml`, run `npm --prefix frontend run types`.
- If you touched `projection.py` or `hashing.py`, say so explicitly in your
  summary. Those two decide whether tags get rewritten, and a subtle bug
  there drains batteries in the field rather than failing a test.