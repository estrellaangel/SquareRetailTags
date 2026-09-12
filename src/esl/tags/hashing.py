import hashlib
import json

from esl.tags.projection import Projection


def hash_projection(projection: Projection) -> str:
    """SHA-256 of the canonical JSON projection.

    Deterministic across processes: sorted keys, integers for money,
    explicit None serialized as JSON null. Never use Python's hash().
    """
    payload = json.dumps(
        {
            "name": projection["name"],
            "variation_name": projection["variation_name"],
            "sku": projection["sku"],
            "price": projection["price"],       # int or None — never float
            "pricing_type": projection["pricing_type"],
        },
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
