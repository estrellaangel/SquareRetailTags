# ESL Pricing Service

A service that keeps electronic shelf labels (ESLs) in sync with prices in
Square, across multiple stores. It reads catalog data from Square, decides
what each shelf tag should display, and hands that "desired state" off to
each store's Raspberry Pi gateway, which is the only thing that actually
talks to that store's tag hardware.

## How it fits together

```
Square (source of truth for price, all locations)
   │  read-only sync
   ▼
ESL Pricing Service  ◄──polls──  Store A's Pi Gateway  ──local HTTP──►  Store A's labels
(this repo, central)             (other dev's code)

                      ◄──polls──  Store B's Pi Gateway  ──local HTTP──►  Store B's labels
                                  (other dev's code)
```

- **Square** owns the price. This service never writes to Square — it only
  reads the catalog via `SearchCatalogObjects`, using a persisted sync
  cursor so it only pulls what changed since the last sync. Square lets a
  price be overridden per location; this service resolves that per store.
- **This service** owns what each tag *should* display, for whichever store
  it's assigned to. It projects the relevant Square fields (name, variation,
  sku, store-resolved price, pricing type) into a `Tag` record, computes a
  deterministic `content_hash` of that projection, and exposes it over
  HTTP, scoped per store.
- **Each store's Pi gateway** (built and owned separately) polls this
  service for its own store's tags, compares `content_hash` to what it last
  rendered, pushes new content to any tag whose hash changed, and reports
  back what it actually displayed. It never invents price data or computes
  hashes itself — it's a dumb, reliable effector. **It is never called by
  this service** — its own local HTTP API is LAN-only and unreachable from
  here (see "Bridging to the real gateway" below), so the relationship is
  always poll-from-the-store, never push-from-the-center.

A webhook from Square (`catalog.version.updated`) can also trigger a sync
immediately instead of waiting for the next scheduled poll.

## Repo layout

| Path | Purpose |
|---|---|
| `src/esl/square/` | Only place allowed to import the Square SDK |
| `src/esl/catalog/` | Square sync jobs, local catalog mirror, per-store price resolution (`pricing.py`) |
| `src/esl/tags/` | Desired-state model, content hashing, drift detection |
| `src/esl/web/` | FastAPI app — the HTTP contract described below |
| `frontend/` | React/Vite admin UI for managing stores and assigning variations to tags |
| `api/esl-pricing-api.yaml` | OpenAPI contract with each store's gateway (authoritative) |
| `api/westgate-store-service.yaml` | Reference copy of the gateway's own local API (what it exposes to itself on the store LAN — not called by this service, see below) |
| `scripts/gateway_sim.py` | Fake gateway for local testing without real hardware |

## Running it locally

```bash
docker compose up -d      # postgres + redis
make migrate               # alembic upgrade head
make dev                   # uvicorn (port 8001) + vite, together
```

`pytest` runs against recorded Square fixtures in `tests/fixtures/square/`,
not the live sandbox.

### Admin login (Auth0)

The dashboard and its backing routes (`/catalog/variations`, `/admin/tags`,
`/stores`, `PUT /tags/{tag_id}`) require an Auth0 login — any authenticated
user gets full access; there are no roles. This is unrelated to the
gateway's `X-Store-Key` (below), which is unaffected.

First time setting up a new environment:

1. Create an Auth0 tenant (free) if you don't have one.
2. **Applications → Create Application → Single Page Application.** Under
   its Settings, set Allowed Callback URLs / Logout URLs / Web Origins to
   `http://localhost:5173` (add your production URL later, comma-separated
   in the same fields). Copy the **Domain** and **Client ID**.
3. **Applications → APIs → Create API.** Any identifier works (e.g.
   `https://esl-pricing-api`) — it doesn't need to resolve to anything.
   Copy the **Identifier**; that's the Audience.
4. Backend — set in `.env`: `AUTH0_DOMAIN`, `AUTH0_AUDIENCE` (see
   `.env.example`).
5. Frontend — set in `frontend/.env`: `VITE_AUTH0_DOMAIN`,
   `VITE_AUTH0_CLIENT_ID`, `VITE_AUTH0_AUDIENCE` (see
   `frontend/.env.example`). These are public SPA identifiers, not
   secrets — normal to ship in the built bundle. No client secret is used
   anywhere; the SPA authenticates via PKCE and the backend verifies token
   signatures against Auth0's public JWKS.

Once both are set, `POST /stores` (and the other admin routes) need a
bearer token — the easiest way to get one for a `curl` test is to open the
dashboard, log in, and copy the token from your browser's network tab, or
just drive everything through the dashboard itself:

```bash
curl -X POST localhost:8001/v1/stores \
  -H 'content-type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"id": "downtown", "name": "Downtown", "square_location_id": "L_ABC123"}'
# → { "id": "downtown", ..., "api_key": "<shown once>" }
```

Then try the central contract without a Pi:

```bash
python scripts/gateway_sim.py --key <api_key> --url http://localhost:8001 --interval 5
```

It polls `/v1/tags` with that store's key, "renders" any tag whose hash
changed, and posts a confirmation back. It only exercises *this service's*
contract, though — see the next section for what a real gateway also has to
do against its own local Pi.

---

## API calls for the Pi gateway

This is the contract the store side needs to implement against *this*
service. Full schema detail lives in `api/esl-pricing-api.yaml` — treat
that file as the source of truth if anything here goes stale. Base path is
`/v1`. Tag ids are 12-character hex, case-insensitive in, upper-case out.

### 1. `GET /tags` — poll for this store's changes

Requires header `X-Store-Key: <this store's api_key>` (from `POST /stores`).
Returns **every** tag belonging to that store — never another store's:

```json
{
  "tags": [
    {
      "id": "A1B2C3D4E5F6",
      "store_id": "downtown",
      "variation_id": "SQ_VAR_123",
      "name": "Cold Brew Concentrate",
      "variation_name": "32 oz",
      "sku": "CB-32",
      "price": 1499,
      "pricing_type": "FIXED_PRICING",
      "content_hash": "9f86d081884c7d65...",
      "last_pushed_at": "2026-09-05T14:02:11Z",
      "last_confirmed_at": "2026-09-05T14:02:14Z",
      "battery_pct": 87
    }
  ]
}
```

`price` is already resolved for this store — if Square has a location
override for this store, it's already applied. The gateway never needs to
know that overrides exist.

**What the gateway should do with it:**
- For each tag, compare `content_hash` to the hash it last rendered for
  that tag ID (keep this in local gateway state — this service doesn't
  track "last rendered by gateway", only "last confirmed").
- If the hash is unchanged, skip it — nothing to do.
- If `content_hash` is `null`, the tag is unassigned.
- Otherwise, render it. **Never divide `price` by 100 for logic, only for
  display** — it's an integer in cents ($14.99 = `1499`).

### 2. `GET /tags/{tag_id}` — fetch one tag

Same auth and shape as above, same store-scoping (404 if the tag belongs to
a different store or doesn't exist). Useful for re-checking one tag without
pulling the whole fleet.

### 3. `POST /tags/{tag_id}/confirm` — report a successful render

Same `X-Store-Key` auth. **Call this immediately after the tag hardware
confirms it displayed the new content.**

```json
// request
{ "content_hash": "9f86d081884c7d65...", "battery_pct": 87 }
```

- `content_hash`: the hash of what was *actually* rendered — i.e. echo
  back the value that came from `/tags`. This is what drift detection is
  built on, so don't fudge it or send a hash the service didn't hand you.
- `battery_pct`: optional (0–100), but send it whenever the tag hardware
  reports one — it's how we'll know when to swap batteries in the field.
- Response is `204 No Content` on success, `404` if `tag_id` is unknown or
  belongs to a different store.

### 4. `GET /health` — liveness check

Returns `{"status": "ok"}`. Fine to use for a startup check or basic
connectivity test from the gateway. No auth required.

### Not for the gateway

- `GET /catalog/variations`, `GET /admin/tags`, `POST /stores`, `PUT
  /tags/{tag_id}` are admin-dashboard calls, gated by Auth0 login (see
  "Admin login" below) — not by `X-Store-Key`. The gateway should never
  need to call these, and couldn't authenticate to them if it tried; it
  only discovers its own assignments through `GET /tags`.

### Suggested gateway loop, against this service

```
every N seconds:
    tags = GET /tags   (X-Store-Key: this store's key)
    for tag in tags:
        if tag.content_hash is None:
            continue                      # unassigned, nothing to show
        if tag.content_hash == last_rendered[tag.id]:
            continue                      # already up to date
        render_to_hardware(tag)           # this is where Westgate comes in — see below
        POST /tags/{tag.id}/confirm { content_hash: tag.content_hash, battery_pct }
        last_rendered[tag.id] = tag.content_hash
```

That's the whole contract with *this* service: poll, compare hashes, render,
confirm. It never needs to know anything about Square, pricing sync, stores,
or how the hash is computed — it just mirrors whatever hash this service
hands it, scoped to its own store.

## Bridging to the real gateway (Westgate)

The gateway's `render_to_hardware(tag)` step above isn't a black box on our
side anymore — its local HTTP API is documented in
`api/westgate-store-service.yaml` (served by the Pi itself, on the store LAN
only, port 5000; unreachable from this service, which is why the gateway
must be the one polling, never the one being called). This is what the
`render_to_hardware` step should actually do:

| This service's `Tag` says... | Call on the Pi (Westgate API) |
|---|---|
| `content_hash` changed, `pricing_type` is `FIXED_PRICING` | `POST /api/labels/{tagId}/product` with a `Display` body: `{ itemName: name, variationName: variation_name, sku, price: { amount: "<price/100 as a decimal string>", currency: "USD" } }` |
| `content_hash` changed, `pricing_type` is `VARIABLE_PRICING` (`price` is `null`) | Westgate's `Display.price` is *required* — there's nothing to put there. Use `POST /api/labels/{tagId}/test?text=<name> — See Register` instead of the product template. |
| `content_hash` changed, tag is unassigned (`content_hash` corresponds to no variation) | `POST /api/labels/{tagId}/unassign` |
| Any push, once queued | The Pi's response is a `LabelUpdate` whose `status` reaches `Succeeded`/`Failed`/`Superseded` — with the default `wait=true` this happens in the same call (blocks up to ~30s). Only call this service's `POST /tags/{tag_id}/confirm` once you have a terminal status, and only for `Succeeded` (use whatever battery/telemetry `GET /api/labels/{tagId}` on the Pi reports for `battery_pct`) |

**Money boundary:** this service's `price` is an integer in cents (never a
float, never divided before rendering — same rule as everywhere else in
this codebase). Westgate's `Money.amount` is a decimal string. Convert with
integer arithmetic, never a float division:

```python
cents = tag["price"]                                    # e.g. 1499
amount = f"{cents // 100}.{cents % 100:02d}"             # "14.99"
```

**Tag id boundary:** both sides now agree — 12 hex characters,
case-insensitive on input, upper-case on output. No conversion needed.

**Note:** the Westgate spec as checked in at
`api/westgate-store-service.yaml` was pasted in during planning and is
missing a few referenced schemas (`LabelUpdate`, `LabelTelemetry`,
`FailureCode`, and others — see the note at the top of that file). Get the
complete file from the gateway team before treating anything past that
point as settled.
