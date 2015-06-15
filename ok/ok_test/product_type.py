# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals

import pytest
from ok.dicts.product_type import ProductType


# noinspection PyUnresolvedReferences
from ok.dicts.term import TypeTerm


@pytest.fixture(autouse=True)
def clear_singleton_cache():
    ProductType.reload()
    assert not ProductType.all_cached_singletons()

def test_singleton_cache():
    t = ProductType('тест')
    assert ProductType.all_cached_singletons() == [t]

    t1 = ProductType('тест')
    assert t1 is t and ProductType.all_cached_singletons() == [t]

    t2 = ProductType('тест', singleton=False)
    assert t2 == t
    assert t2 is not t
    assert ProductType.all_cached_singletons() == [t]

    t3 = ProductType('тест', singleton=False)
    assert t3 == t2
    assert t3 is not t2 and t3 is not t
    assert ProductType.all_cached_singletons() == [t]

    t4 = ProductType('тест_', singleton=False)
    assert t4 != t3
    assert ProductType.all_cached_singletons() == [t]


def test_singleton_cache_make_from_terms():
    term = TypeTerm.make('тест')
    t = ProductType.make_from_terms([term])
    assert ProductType.all_cached_singletons() == [t]

    t1 = ProductType.make_from_terms([term])
    assert t1 is t and ProductType.all_cached_singletons() == [t]


def test_relations_sort():
    t1 = ProductType('тест1')
    t2 = ProductType('тест2')
    t3 = ProductType('тест3')
    t4 = ProductType('тест4')
    t5 = ProductType('тест5')
    t6 = ProductType('тест6')

    r1 = t1.similar(t5, 0.3)
    r2 = t1.similar(t6, 0.31)
    r3 = t1.almost(t2, 0.1, 0.9)
    r4 = t1.almost(t3, 0.99, 0.01)
    r5 = t1.equals_to(t4)

    rel = t1.relations()
    assert rel == [r4, r3, r5, r2, r1]