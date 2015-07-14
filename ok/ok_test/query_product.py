# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
from collections import defaultdict

import logging
import pytest
from ok.dicts.term import TypeTerm

from ok.query.product import ProductQuery, ProductQueryParser
from ok.dicts.product_type import ProductType

app_log = logging.getLogger('ok')
app_log.setLevel(logging.DEBUG)
app_log.addHandler(logging.StreamHandler())


@pytest.fixture(scope='module')
def term_dict():
    from ok.dicts import term
    return term.load_term_dict()


def test_pfqn_parse_fat():
    pq = ProductQueryParser('продукт(10 % жирн) с соком')

    assert pq.fat() == '10 % жирн'
    assert pq.remaining_tokens() == 'продукт с соком'.split()


def test_pfqn_parse_fat_complex():
    pq = ProductQueryParser('Продукт творож 5.6%130г клубника+бисквит')

    assert pq.fat() == '5.6%'
    assert pq.weight() == '130г'
    assert pq.remaining_tokens() == 'продукт творож клубника бисквит'.split()


def test_pfqn_parse_plain_percent():
    pq = ProductQueryParser('продукт % с соком')

    assert pq.fat() is None
    assert pq.remaining_tokens() == 'продукт % с соком'.split()


def test_pfqn_parse_pack():
    pq = ProductQueryParser('чай 25пак с жасмином')

    assert pq.fat() is None
    assert pq.pack() == '25пак'
    assert pq.remaining_tokens() == 'чай с жасмином'.split()


def test_pfqn_parse_pack_bounded_separator():
    pq = ProductQueryParser('чай пакетированный')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.remaining_tokens() == 'чай пакетированный'.split()


def test_pfqn_parse_pack_bounded_end_of_string():
    pq = ProductQueryParser('Кофе растворимый 150г пакет')

    assert pq.fat() is None
    assert pq.weight() == '150г'
    assert pq.pack() == 'пакет'
    assert pq.remaining_tokens() == 'кофе растворимый'.split()


def test_pfqn_parse_pack_prebounded_separator():
    # Check pack 'уп.'
    pq = ProductQueryParser('кетчуп.')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.remaining_tokens() == 'кетчуп'.split()


def test_pfqn_parse_weight():
    pq = ProductQueryParser('сахар 1 кг. коричневый')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.weight() == '1 кг.'
    assert pq.remaining_tokens() == 'сахар коричневый'.split()


def test_pfqn_parse_weight_short():
    pq = ProductQueryParser('сахар кг., коричневый')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.weight() == 'кг.'
    assert pq.remaining_tokens() == 'сахар коричневый'.split()


def test_pfqn_parse_weight_bounded_from_non_digit():
    pq = ProductQueryParser('сахар1 кг. корич.')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.weight() == '1 кг.'
    assert pq.remaining_tokens() == 'сахар корич'.split()


def test_pfqn_parse_weight_short_prebounded_separator():
    pq = ProductQueryParser('масл.')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.weight() is None
    assert pq.remaining_tokens() == 'масл'.split()

    pq = ProductQueryParser('мас л.')
    assert pq.weight() == 'л.'


def test_pfqn_parse_not_weight_short_postbounded_separator():
    pq = ProductQueryParser('рыба г/к')

    assert pq.fat() is None
    assert pq.pack() is None
    assert pq.weight() is None
    assert pq.remaining_tokens() == 'рыба г/к'.split()

    pq = ProductQueryParser('рыба /125 г/')
    assert pq.weight() == '125 г'

# ProductQuery tests


class MockProductQuery(ProductQuery):
    pass


def test_product_pfqn_query_with_simple_brand():
    pfqn = 'йогурт 5% эрмигурт 125 г с вишней'

    old_parse_brand = MockProductQuery.parse_brand

    def parse_brand(_, remain):
        assert remain, 'йогурт эрмигурт с вишней'.split()
        return 'Эрмигурт', [remain[0], remain[2], remain[3]]
    MockProductQuery.parse_brand = classmethod(parse_brand)

    def type_filter(p_types):
        for p_type in p_types:
            if TypeTerm.make('вишня').term_id in p_type or p_type == (TypeTerm.make('йогурт').term_id,):
                yield p_type

    pq = MockProductQuery.from_pfqn(pfqn, type_filter=type_filter)
    assert pq.fat == '5%'
    assert pq.weight == '125 г'
    assert pq.brand == 'Эрмигурт'
    assert pq.sqn == 'йогурт с вишней'.split()
    assert pq.types == {ProductType('йогурт',), ProductType('йогурт', 'вишня')}

    # Tear down
    MockProductQuery.parse_brand = old_parse_brand


# FULL tests

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


#@pytest.mark.xfail(reason='still working on brands data washing out as well as product type vs brand scoring')
def test_pfqn_query_all_meta_products_sqn_full():
    """
    Main dis-match reasons:
    1. False positive brand match on product type terms ('филе' vs 'Филевский')
    2. Brand generic has not been used on replacement
    3. NoBrand garbage tokens in pfqn (like PF PL)
    4. Brand misspelling - no appropriate synonym in Brand dict for all used spellings ('Лаймон фрэш' vs 'Лаймон фреш')
    5. Joined words - incorrect token definition in token parser (GreenfieldФестив)
    """
    from ok.dicts import main_options
    from ok.dicts.product import Product

    query_log = logging.getLogger('ok.query')
    query_log_level = query_log.level
    query_log.setLevel(logging.WARN)

    import time
    start = time.time()
    fail_count = total = 0
    brands_failed = defaultdict(int)
    false_brands = defaultdict(int)

    try:
        config = main_options([])
        products = Product.from_meta_csv(config.products_meta_in_csvname)
        ae = None
        for p in products:
            pq = ProductQuery.from_pfqn(p.pfqn)
            sqn_query = pq.sqn_query()
            parsed_sqn = sqn_query.to_str(' ')
            total += 1
            try:
                assert p.sqn == parsed_sqn
            except AssertionError as ae:
                reason = ''
                if p['brand_detected'] and pq.brand and p['brand'] != pq.brand:
                    reason = 'false brand'
                    false_brands[pq.brand] += 1

                print("Assert failed[%s]: pfqn['%s'], brand: %s. SQN meta='%s', parsed='%s'" % (reason, p.pfqn, p['brand'], p.sqn, parsed_sqn))
                fail_count += 1
                brands_failed[p['brand']] += 1
        if ae:
            raise AssertionError("Failed to match %d of %d products (%d%%)" % (fail_count, total, fail_count * 100 // total))
    finally:
        # Tear down
        query_log.setLevel(query_log_level)
        if total > 0:
            elapsed = time.time() - start
            app_log.log(logging.INFO, "Parsed %d products. Time elapsed: %ds (%0.3fs per product)" % (total, elapsed, elapsed/total))

            for brand, b_failed in sorted(brands_failed.items(), key=lambda t: t[1], reverse=True):
                app_log.log(logging.INFO, "Brand %s failed: %d" % (brand, b_failed))

            app_log.log(logging.INFO, '=' * 40, ' FALSE BRANDS: %d total' % sum(false_brands.values()))
            for brand, b_failed in sorted(false_brands.items(), key=lambda t: t[1], reverse=True):
                app_log.log(logging.INFO, "False Brand %s: %d" % (brand, b_failed))

def test_feeder_extract_sqn_tail_full(term_dict):

    sqn = 'продукт йогуртный экстра сливочный клубн/земл'
    p_types = set(map(lambda t: ProductType(*t), (("йогурт",), ("йогурт", "земляника"), ("йогурт", "клубника"),
                                 ("продукт",), ("продукт", "йогуртный", "сливочный"), ("продукт", "йогуртный", "экстра")))
                  )
    pq = ProductQuery.from_product({'sqn': sqn, 'types': p_types})
    tail = pq.tail

    assert tail == []


def test_product_pfqn_query_with_simple_brand_full():
    pfqn = 'йогурт 5% эрмигурт 125 г с вишней'

    def type_filter(p_types):
        for p_type in p_types:
            if TypeTerm.make('вишня').term_id in p_type or p_type == (TypeTerm.make('йогурт').term_id,):
                yield p_type

    pq = ProductQuery.from_pfqn(pfqn, type_filter=type_filter)

    assert pq.fat == '5%'
    assert pq.weight == '125 г'
    assert pq.brand == 'Эрмигурт'
    assert pq.sqn == 'йогурт с вишней'.split()
    assert pq.types == {ProductType('йогурт',), ProductType('йогурт', 'вишня')}


def test_product_pfqn_query_with_multi_token_brand_full():
    pfqn = 'молоко 2,5 % жирн домик в деревне 0,9л'

    pq = ProductQuery.from_pfqn(pfqn)

    assert pq.fat == '2,5 % жирн'
    assert pq.weight == '0,9л'
    assert pq.brand == 'Домик в деревне'
    assert pq.sqn == 'молоко'.split()
    assert pq.types == {ProductType('молоко',)}

def test_product_pfqn_query_english_brand_full():
    pfqn = 'Горчица Французская "Хайнц" стекло 180 г'

    pq = ProductQuery.from_pfqn(pfqn)

    assert pq.weight == '180 г'
    assert pq.brand == 'Heinz'
    assert pq.sqn == 'горчица французская стекло'.split()
    assert ProductType('горчица', 'французская') in pq.types

def test_product_pfqn_query_false_brand_as_type():
    pfqn = 'Филе треск. с/м в панировке'

    pq = ProductQuery.from_pfqn(pfqn)

    assert pq.brand is None
    assert pq.sqn == 'Филе треск с/м в панировке'.split()
    assert ProductType('филе', 'трески') in pq.types
