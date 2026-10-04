from esl.catalog.models import CatalogVariation, CatalogVariationLocationPrice
from esl.catalog.pricing import resolve_price


def _variation(price: int | None, overrides: list[CatalogVariationLocationPrice] | None = None) -> CatalogVariation:
    variation = CatalogVariation(
        id="VAR1",
        item_id="ITEM1",
        variation_name="Regular",
        price=price,
        pricing_type="FIXED_PRICING",
    )
    variation.location_prices = overrides or []
    return variation


def test_falls_back_to_flat_price_when_no_override():
    variation = _variation(price=1499)
    assert resolve_price(variation, "L_STORE_A") == 1499


def test_uses_override_for_matching_location():
    override = CatalogVariationLocationPrice(
        variation_id="VAR1", square_location_id="L_STORE_A", price=1299
    )
    variation = _variation(price=1499, overrides=[override])
    assert resolve_price(variation, "L_STORE_A") == 1299


def test_ignores_override_for_a_different_location():
    override = CatalogVariationLocationPrice(
        variation_id="VAR1", square_location_id="L_STORE_B", price=1299
    )
    variation = _variation(price=1499, overrides=[override])
    assert resolve_price(variation, "L_STORE_A") == 1499


def test_none_price_passes_through_for_variable_pricing():
    variation = _variation(price=None)
    assert resolve_price(variation, "L_STORE_A") is None
