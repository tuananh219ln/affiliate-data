from decimal import Decimal

from affiliate_data.models import Product
from affiliate_data.ranking import rank


def _product(n: int, price: int | None, rate: float | None, sold: int | None = None) -> Product:
    return Product(
        id=n, platform="shopee", external_id=str(n), name=f"SP {n}", price=price, commission_rate=rate, sold=sold
    )


def _ids(ranked):
    return [p.external_id for p, _ in ranked]


PRODUCTS = [
    _product(1, 200_000, 0.03),  # dear, low commission
    _product(2, 100_000, 0.05),  # cheapest, middling commission
    _product(3, 150_000, 0.10),  # middling price, highest commission
]


def test_cheap_and_well_paid_comes_first():
    ranked = rank(PRODUCTS, top=3)
    assert _ids(ranked) == ["3", "2", "1"]
    assert [score for _, score in ranked] == [0.75, 0.6429, 0.0]


def test_price_weight_ranks_by_price_or_by_commission_alone():
    assert _ids(rank(PRODUCTS, top=3, price_weight=1)) == ["2", "3", "1"]
    assert _ids(rank(PRODUCTS, top=3, price_weight=0)) == ["3", "2", "1"]


def test_top_limits_the_list():
    assert _ids(rank(PRODUCTS, top=1)) == ["3"]


def test_products_without_price_or_commission_are_left_out():
    products = [_product(1, None, 0.1), _product(2, 0, 0.1), _product(3, 100, None), _product(4, 100, 0.02)]
    assert _ids(rank(products, top=5)) == ["4"]
    assert rank([_product(1, None, None)], top=5) == []


def test_equal_scores_prefer_the_better_seller():
    products = [_product(1, 100, 0.1, sold=10), _product(2, 100, 0.1, sold=900), _product(3, 100, 0.1)]
    ranked = rank(products, top=3)
    assert _ids(ranked) == ["2", "1", "3"]
    assert {score for _, score in ranked} == {1.0}


def test_prices_may_be_decimals():
    products = [_product(1, Decimal("99.50"), 0.1), _product(2, Decimal("120.00"), 0.1)]
    assert _ids(rank(products, top=2, price_weight=1)) == ["1", "2"]
