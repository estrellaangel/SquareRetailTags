# ESL Pricing Service

Syncs pricing from Square (read-only) and publishes desired state for
electronic shelf labels. Each store runs its own Raspberry Pi gateway, owned
by the other developer, which polls this service and drives that store's tag
hardware. The Pi's own local API (what it exposes on the store LAN to
actually push to labels) is `api/westgate-store-service.yaml` — that's the
gateway's contract with its hardware, not with us; it's checked in here only
as a reference for writing the README's gateway-bridging docs.

<!-- Detailed Square SDK and frontend rules are path-scoped in .claude/rules/ -->

## Architecture

- Square is the source of truth for price. This service is READ-ONLY against
  the catalog. Never write to Square.
- This service is the source of truth for what each tag displays.
- The business runs multiple stores. Every tag belongs to exactly one store
  (`tags.store_id`), and price is resolved per-store: Square's
  `location_overrides` can override the flat catalog price for a specific
  location, so the same variation can project to a different price — and a
  different `content_hash` — in different stores. See
  `src/esl/catalog/pricing.py::resolve_price`.
- The gateway is an effector: it renders and pushes, and reports back what it
  displayed. It never originates price data or computes hashes. It cannot be
  reached from this service — its HTTP API is store-LAN-only — so it's always
  the gateway polling us (`GET /tags` with its store's `X-Store-Key`), never
  us calling out to it.
- `api/esl-pricing-api.yaml` is the contract with the gateway. Treat it as
  authoritative. Changing an endpoint means changing the spec first.
- The admin dashboard's own routes (`/catalog/variations`, `/admin/tags`,
  `/stores`, `PUT /tags/{tag_id}`) require an Auth0 bearer token
  (`src/esl/web/auth.py::get_current_user`) — any authenticated user, no
  roles. This is unrelated to the gateway's `X-Store-Key`
  (`get_current_store` in `tags.py`): gateways are software polling a fixed
  endpoint and can't complete an OAuth redirect, so `GET /tags`, `GET
  /tags/{tag_id}`, and `POST /tags/{tag_id}/confirm` stay on `X-Store-Key`
  only. Don't put Auth0 on those, and don't put `X-Store-Key` on admin
  routes.

## Layout

- `src/esl/square/` — the ONLY package permitted to import the Square SDK.
  Everything else works with internal dataclasses.
- `src/esl/catalog/` — sync jobs, the Square mirror, and per-store price
  resolution (`pricing.py`).
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
  `projection.build_projection` takes an already store-resolved `price` —
  never read `variation.price` directly when building or rehashing a tag's
  projection, or you'll skip location overrides.
- Content hashing must be deterministic across processes and restarts:
  sorted keys, integers for money, explicit null handling. Never use Python's
  builtin `hash()`.
- Tag IDs are normalized to 12-char uppercase hex at the API boundary — this
  matches the real ESL hardware id length (confirmed against
  `api/westgate-store-service.yaml`), not the 16 chars this repo assumed
  before that spec existed.

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