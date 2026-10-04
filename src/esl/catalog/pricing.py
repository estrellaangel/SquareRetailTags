from esl.catalog.models import CatalogVariation


def resolve_price(variation: CatalogVariation, square_location_id: str) -> int | None:
    """Effective price for a variation at a given store's Square location.

    A location override (from Square's `location_overrides`) takes precedence;
    otherwise the flat `variation.price` applies. Both are integer cents, or
    None when `pricing_type` is VARIABLE_PRICING.
    """
    for override in variation.location_prices:
        if override.square_location_id == square_location_id:
            return override.price
    return variation.price
