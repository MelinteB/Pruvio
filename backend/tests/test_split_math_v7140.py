import pytest
from app.services import split_math_v7140 as math


def test_equal_1_cent_3_participants():
    values = math.equal_minor(1, ['z', 'a', 'b'])
    assert values == {'a': 1, 'b': 0, 'z': 0}
    assert sum(values.values()) == 1


def test_equal_receipt_including_tax_tip_charge():
    # Total of all bill components; exact sum preserved.
    values = math.equal_minor(10001, ['owner', 'guest2', 'guest3'])
    assert sum(values.values()) == 10001
    assert max(values.values()) - min(values.values()) <= 1


def test_two_pizzas_shared_among_four():
    values = math.shared_item_minor('2', 4000, ['p1','p2','p3','p4'])
    assert values == {'p1': 2000, 'p2': 2000, 'p3': 2000, 'p4': 2000}


def test_custom_proportions_exact_total():
    values = math.proportional_minor(101, {'a':'0.5','b':'0.3','c':'0.2'})
    assert sum(values.values()) == 101
    assert values == {'a': 51, 'b': 30, 'c': 20}


def test_rerender_order_does_not_change_money():
    assert math.equal_minor(100, ['c','a','b']) == math.equal_minor(100, ['b','c','a'])


def test_zero_value_line_item():
    assert math.shared_item_minor('2', 0, ['a','b','c']) == {'a': 0, 'b': 0, 'c': 0}


@pytest.mark.parametrize('bad', ['1.001','-1','NaN','Infinity','nope'])
def test_invalid_currency_value_rejected(bad):
    with pytest.raises(ValueError): math.to_minor(bad)


def test_decimal_to_minor():
    assert math.to_minor('80.00') == 8000


def test_legacy_item_quantity_does_not_cap_sharers():
    assert sum(math.shared_item_minor('1', 125, ['a','b','c','d']).values()) == 125


def test_proportional_bad_weight_rejected():
    with pytest.raises(ValueError): math.proportional_minor(100, {'a': '0','b':'1'})
