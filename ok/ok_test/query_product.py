# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

import pytest

from ok.query.product import ProductQuery, ProductQueryParser
from ok.dicts.product_type import ProductType


@pytest.fixture(scope='module')
def term_dict():
    from ok.dicts import term
    return term.load_term_dict()


def test_pfqn_parse_fat():
    pq = ProductQueryParser('продукт(10 % жирн) с соком')

    assert pq.fat() == '10 % жирн'
    assert pq.remaining_tokens() == 'продукт с соком'


def test_pfqn_parse_fat_complex():
    pq = ProductQueryParser('Продукт творож 5.6%130г клубника+бисквит')

    assert pq.fat() == '5.6%'
    assert pq.weight() == '130г'
    assert pq.remaining_tokens() == 'продукт творож клубника бисквит'


def test_pfqn_parse_plain_percent():
    pq = ProductQueryParser('продукт % с соком')

    assert pq.fat() is None
    assert pq.remaining_tokens() == 'продукт % с соком'


def test_pfqn_parse_pack():
    pq = ProductQueryParser('чай 25пак с жасмином')

    assert pq.fat() is None
    assert pq.pack() == '25пак'
    assert pq.remaining_tokens() == 'чай с жасмином'


def test_pfqn_parse_pack_bounded_separator():
    pq = ProductQueryParser('чай пакетированный')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.remaining_tokens() == 'чай пакетированный'


def test_pfqn_parse_pack_bounded_end_of_string():
    pq = ProductQueryParser('Кофе растворимый 150г пакет')

    assert pq.fat() is None
    assert pq.weight() == '150г'
    assert pq.pack() == 'пакет'
    assert pq.remaining_tokens() == 'кофе растворимый'


def test_pfqn_parse_pack_prebounded_separator():
    # Check pack 'уп.'
    pq = ProductQueryParser('кетчуп.')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.remaining_tokens() == 'кетчуп'


def test_pfqn_parse_weight():
    pq = ProductQueryParser('сахар 1 кг. коричневый')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.weight() == '1 кг.'
    assert pq.remaining_tokens() == 'сахар коричневый'


def test_pfqn_parse_weight_short():
    pq = ProductQueryParser('сахар кг., коричневый')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.weight() == 'кг.'
    assert pq.remaining_tokens() == 'сахар коричневый'


def test_pfqn_parse_weight_bounded_from_non_digit():
    pq = ProductQueryParser('сахар1 кг. корич.')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.weight() == '1 кг.'
    assert pq.remaining_tokens() == 'сахар корич'


def test_pfqn_parse_weight_short_prebounded_separator():
    pq = ProductQueryParser('масл.')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.weight() is None
    assert pq.remaining_tokens() == 'масл'

    pq = ProductQueryParser('мас л.')
    assert pq.weight() == 'л.'


@pytest.mark.xfail(reason='meta product parser must be refactored and query.product parser has to be used instead of legacy')
def test_pfqn_parse_all_meta_products_full():
    from ok.dicts import main_options
    from ok.dicts.product import Product

    fields = ['weight', 'fat', 'pack']
    config = main_options([])
    products = Product.from_meta_csv(config.products_meta_in_csvname)
    ae = None
    for p in products:
        pq = ProductQueryParser(p.pfqn)
        parsed = dict(zip(fields, (pq.weight(), pq.fat(), pq.pack())))
        for f in fields:
            try:
                assert (not p[f] and not parsed[f]) or (p[f] and parsed[f] and (p[f] == parsed[f] or p[f] == parsed[f] + '.'))
            except AssertionError as ae:
                print("Assert failed: pfqn['%s']. Field '%s': meta='%s', parsed='%s'" % (p.pfqn, f, p[f], parsed[f]))
    if ae:
        raise ae


def test_feeder_extract_sqn_tail_full(term_dict):

    sqn = 'продукт йогуртный экстра сливочный клубн/земл'
    p_types = set(map(lambda t: ProductType(*t), (("йогурт",), ("йогурт", "земляника"), ("йогурт", "клубника"),
                                 ("продукт",), ("продукт", "йогуртный", "сливочный"), ("продукт", "йогуртный", "экстра")))
                  )
    pq = ProductQuery.from_product({'sqn': sqn, 'types': p_types})
    tail = pq.tail

    assert tail == []


