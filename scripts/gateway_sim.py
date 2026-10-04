"""
Pi Gateway Simulator — local testing only.

Simulates one store's gateway polling this service's central contract
(GET /tags, POST /tags/{id}/confirm) and "rendering" whatever it finds. It
does not model the real Westgate store-service API the gateway speaks to
its own local Pi (see api/westgate-store-service.yaml and README.md) —
in particular it never distinguishes FIXED_PRICING from VARIABLE_PRICING
the way a real gateway must (see README.md's placeholder-text note).

Usage:
    python scripts/gateway_sim.py --key <store api_key> [--url http://localhost:8001] [--interval 5]
"""
import argparse
import asyncio
import logging
import random

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gateway_sim")


async def run(base_url: str, interval: int, store_key: str) -> None:
    # tag_id → {rendered_hash, battery_pct}
    state: dict[str, dict] = {}

    headers = {"X-Store-Key": store_key}
    async with httpx.AsyncClient(base_url=base_url, timeout=10, headers=headers) as client:
        log.info("Gateway sim started — polling %s every %ds", base_url, interval)

        while True:
            try:
                resp = await client.get("/v1/tags")
                resp.raise_for_status()
                tags = resp.json()["tags"]
            except Exception as exc:
                log.warning("Poll failed: %s", exc)
                await asyncio.sleep(interval)
                continue

            for tag in tags:
                tag_id = tag["id"]
                desired_hash = tag.get("content_hash")

                if desired_hash is None:
                    continue  # unassigned tag, nothing to render

                if tag_id not in state:
                    # First time seeing this tag — initialise with a random battery
                    state[tag_id] = {
                        "rendered_hash": None,
                        "battery_pct": random.randint(60, 100),
                    }

                s = state[tag_id]

                if s["rendered_hash"] == desired_hash:
                    continue  # already up to date

                # Simulate rendering
                name = tag.get("name") or "???"
                price = tag.get("price")
                price_str = (
                    f"${price / 100:.2f}" if price is not None else "variable"
                )
                log.info(
                    "RENDER  %s  →  %s  %s  (hash %s…)",
                    tag_id,
                    name[:40],
                    price_str,
                    desired_hash[:8],
                )

                # Drain battery slightly on each render
                s["battery_pct"] = max(
                    0, s["battery_pct"] - round(random.uniform(0.1, 0.5), 1)
                )
                battery = round(s["battery_pct"])

                # Confirm render back to service
                try:
                    confirm = await client.post(
                        f"/v1/tags/{tag_id}/confirm",
                        json={"content_hash": desired_hash, "battery_pct": battery},
                    )
                    confirm.raise_for_status()
                    s["rendered_hash"] = desired_hash
                    log.info(
                        "CONFIRM %s  battery=%d%%",
                        tag_id,
                        battery,
                    )
                except Exception as exc:
                    log.warning("Confirm failed for %s: %s", tag_id, exc)

            await asyncio.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="ESL gateway simulator")
    parser.add_argument(
        "--key",
        required=True,
        help="Store api_key, from POST /stores (sent as X-Store-Key)",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8001",
        help="Base URL of the ESL pricing service",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Poll interval in seconds (default: 5)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.url, args.interval, args.key))


if __name__ == "__main__":
    main()
