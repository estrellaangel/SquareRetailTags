import pytest

from esl.tags.commands import build_display, currency_exponent, money_amount
from esl.tags.projection import Projection


def _projection(price, name="Cold Brew", variation="32 oz", sku="CB-32"):
    return Projection(
        name=name,
        variation_name=variation,
        sku=sku,
        price=price,
        pricing_type="FIXED_PRICING" if price is not None else "VARIABLE_PRICING",
    )


# ── money_amount ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cents,expected",
    [
        (1999, "19.99"),
        (11100, "111.00"),
        (2645, "26.45"),
        (100, "1.00"),
        (99, "0.99"),
        (9, "0.09"),
        (0, "0.00"),
        (21999, "219.99"),
    ],
)
def test_usd_renders_as_two_decimal_string(cents, expected):
    assert money_amount(cents, "USD") == expected


def test_zero_decimal_currency_has_no_point():
    assert money_amount(1500, "JPY") == "1500"


def test_three_decimal_currency():
    assert money_amount(1500, "KWD") == "1.500"


def test_negative_amount_keeps_sign():
    assert money_amount(-1999, "USD") == "-19.99"


def test_result_is_a_string_never_a_float():
    """Floats are banned end to end; the gateway's Money.amount is a string."""
    assert isinstance(money_amount(1999, "USD"), str)


def test_unknown_currency_defaults_to_two_decimals():
    assert currency_exponent("ZZZ") == 2
    assert money_amount(1999, "ZZZ") == "19.99"


# ── build_display ───────────────────────────────────────────────────────


def test_display_carries_currency_and_decimal_amount():
    display = build_display(_projection(1999), "USD")
    assert display["price"] == {"amount": "19.99", "currency": "USD"}
    assert display["itemName"] == "Cold Brew"
    assert display["variationName"] == "32 oz"
    assert display["sku"] == "CB-32"


def test_display_passes_regular_through_untouched():
    """The gateway's spec says it decides what to hide, not us."""
    display = build_display(_projection(1999, variation="Regular"), "USD")
    assert display["variationName"] == "Regular"


def test_empty_variation_name_becomes_null_not_empty_string():
    display = build_display(_projection(1999, variation=""), "USD")
    assert display["variationName"] is None


def test_variable_pricing_cannot_build_a_display():
    """Display.price is required, so a null price has no valid payload."""
    with pytest.raises(ValueError, match="variable-priced"):
        build_display(_projection(None), "USD")
