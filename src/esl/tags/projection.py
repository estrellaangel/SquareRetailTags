from typing import TypedDict

from esl.catalog.models import CatalogItem, CatalogVariation


class Projection(TypedDict):
    name: str | None
    variation_name: str | None
    sku: str | None
    price: int | None  # integer cents; None when VARIABLE_PRICING
    pricing_type: str | None


def build_projection(item: CatalogItem, variation: CatalogVariation) -> Projection:
    return Projection(
        name=item.name,
        variation_name=variation.variation_name,
        sku=variation.sku,
        price=variation.price,
        pricing_type=variation.pricing_type,
    )


UNASSIGNED: Projection = Projection(
    name=None,
    variation_name=None,
    sku=None,
    price=None,
    pricing_type=None,
)
