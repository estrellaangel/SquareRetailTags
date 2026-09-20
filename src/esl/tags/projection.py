from typing import TypedDict

from esl.catalog.models import CatalogItem, CatalogVariation


class Projection(TypedDict):
    name: str | None
    variation_name: str | None
    sku: str | None
    price: int | None  # integer cents; None when VARIABLE_PRICING
    pricing_type: str | None


def build_projection(
    item: CatalogItem, variation: CatalogVariation, price: int | None
) -> Projection:
    """`price` must already be resolved for the tag's store — see
    `esl.catalog.pricing.resolve_price`. This function never reads
    `variation.price` directly so a caller can't accidentally use the
    flat, non-location-aware price.
    """
    return Projection(
        name=item.name,
        variation_name=variation.variation_name,
        sku=variation.sku,
        price=price,
        pricing_type=variation.pricing_type,
    )


UNASSIGNED: Projection = Projection(
    name=None,
    variation_name=None,
    sku=None,
    price=None,
    pricing_type=None,
)
