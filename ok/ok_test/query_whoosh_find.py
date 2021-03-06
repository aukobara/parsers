# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

import logging

import pytest
from whoosh.filedb.filestore import RamStorage

import ok.query.find as oq_find
from ok.query.whoosh_contrib import find_products, find_brands

app_log = logging.getLogger('ok')
app_log.setLevel(logging.DEBUG)
app_log.addHandler(logging.StreamHandler())


@pytest.fixture(scope='module')
def ix_prod_full():
    from whoosh.filedb.filestore import RamStorage
    from ok.query.whoosh_contrib import indexes

    st = RamStorage()

    if indexes.INDEX_PRODUCTS in indexes.indexes:
        del indexes.indexes[indexes.INDEX_PRODUCTS]
    ix = indexes.init_index(st, one_index=indexes.INDEX_PRODUCTS)
    return ix

@pytest.fixture(scope='module')
def ix_brand_full():
    from whoosh.filedb.filestore import RamStorage
    from ok.query.whoosh_contrib import indexes

    st = RamStorage()

    if indexes.INDEX_BRANDS in indexes.indexes:
        del indexes.indexes[indexes.INDEX_BRANDS]
    ix = indexes.init_index(st, one_index=indexes.INDEX_BRANDS)
    return ix


@pytest.fixture(scope='module')
def ix_full(ix_prod_full, ix_brand_full):
    return ix_prod_full, ix_brand_full

@pytest.fixture
def ix_test_docs():
    return [{'pfqn': "тест", 'types': ['тест']}]


@pytest.fixture
def ix_test(ix_test_docs):
    from whoosh.filedb.filestore import RamStorage
    from ok.query.whoosh_contrib import indexes

    st = RamStorage()

    # Clear all indexes before any test and recreate them in memory
    indexes.indexes.clear()
    orig_index_def = dict(indexes.index_def_dict)

    def test_feeder(writer):
        """@param whoosh.writing.IndexWriter writer: index writer"""
        for doc in ix_test_docs:
            writer.add_document(**doc)
        return 1

    indexes.index_def_dict[indexes.INDEX_PRODUCTS] = \
        indexes.IndexDef(orig_index_def[indexes.INDEX_PRODUCTS].schema, test_feeder, lambda: 1, [indexes.find_products.FindProductsQuery])

    ix = indexes.init_index(st, one_index=indexes.INDEX_PRODUCTS)

    # Restore original schema
    indexes.index_def_dict.update(orig_index_def)

    return ix


@pytest.fixture
def ix_test_many():
    docs = [
        {'pfqn': "тест", 'types': ['тест'], 'brand': 'бренд1'},
        {'pfqn': "тестовый", 'types': ['тест'], 'brand': 'бренд2'},
        {'pfqn': "тест тест2", 'types': ['тест', 'тест2', 'тест + тест2'], 'brand': 'бренд1'},
        {'pfqn': "тест3", 'types': ['тест3'], 'brand': 'бренд2'},
    ]
    return ix_test(docs)


def test_simple(ix_test):
    with oq_find.find_products('тест', return_fields=['pfqn']) as rs:
        assert rs.size == 1
        assert 'тест' == next(rs.data)


def test_select_one(ix_test_many):
    with oq_find.find_products('тест2 тест', return_fields=['pfqn']) as rs:
        assert rs.size == 1
        assert 'тест тест2' == next(rs.data)


def test_facets(ix_test_many):
    with oq_find.find_products('тест', return_fields=['pfqn'], facet_fields=['brand']) as rs:
        assert rs.size > 1
        assert 'тест' in rs.data
        facet_counts = rs.facet_counts('brand')
        assert facet_counts and len(facet_counts) == 2
        assert sum(facet_counts.values()) == rs.size
        assert facet_counts == {'бренд1': 2, 'бренд2': 1}

def test_find_products_full(ix_prod_full):
    with oq_find.find_products('масло', return_fields=['types']) as rs:
        assert rs.size > 0
        assert all('масло' in types for types in rs.data)

def test_find_products_wpf_full(ix_prod_full):
    with oq_find.find_products('Масло слив 82.5% 180г', return_fields=['pfqn', 'types']) as rs:
        assert rs.size > 0
        assert all('масло' in types for pfqn, types in rs.data)

def test_find_products_no_dup_queries(ix_test_many):
    fq = find_products.FindProductsQuery('тест тест2 тест1234 35% 180г упаковка')
    try:
        q_list = fq.query_variants()
        assert len(q_list) == len(set(q.normalize() for q in q_list))
    finally:
        fq.close()

def test_find_products_filter_known_types(ix_test_many):
    fq = find_products.FindProductsQuery('тест тест2 тест1234')
    try:
        q_list = fq.query_variants()
        for q in q_list:
            for term in q.iter_all_terms():
                if term[0] == 'types':
                    assert term[1] in ('тест', 'тест2', 'тест + тест2')
    finally:
        fq.close()

class writer_mock(object):

    def __init__(self):
        self.doc_fields = None

    def add_document(self, **kwargs):
        self.doc_fields = self.doc_fields or []
        self.doc_fields.append(dict(kwargs))

def test_feeder():
    from ok.dicts.product import Product
    from ok.dicts.product_type import ProductType

    p = Product(sqn='тест1 хвост', pfqn='тест1 большой хвост 3,5% 10 шт 0,125 г', types={ProductType('тест1', 'тест2')},
                brand='бренд', brand_detected=False, fat='3,5%', pack='10 шт', weight='0,125 г')
    writer = writer_mock()

    find_products.feed_product(p, writer)

    assert writer.doc_fields
    assert len(writer.doc_fields) == 1
    fields = writer.doc_fields[0]
    assert fields['pfqn'] == 'тест1 большой хвост 3,5% 10 шт 0,125 г'
    assert fields['types'] == ['тест1 + тест2']
    assert fields['tail'] == ['хвост']
    assert fields['brand'] == 'бренд'
    assert fields['fat'] == ['3,5%']
    assert fields['pack'] == ['10 шт']
    assert fields['weight'] == ['0,125 г']
    # Check no other fields passed to writer
    assert len(fields) == 7

def test_index_does_not_recreated_if_no_changes_full(ix_prod_full):
    """@param whoosh.index.FileIndex ix_prod_full: test index in ram storage"""
    from ok.query.whoosh_contrib import indexes
    from whoosh.fields import TEXT

    assert ix_prod_full.schema
    original_schema = find_products.SCHEMA
    orig_index_def = dict(indexes.index_def_dict)
    assert ix_prod_full.schema == original_schema and original_schema == orig_index_def[indexes.INDEX_PRODUCTS].schema

    assert isinstance(ix_prod_full.storage, RamStorage)
    existing_files = dict(ix_prod_full.storage.files)

    # Reopen index
    del indexes.indexes[indexes.INDEX_PRODUCTS]
    ix2 = indexes.init_index(ix_prod_full.storage, one_index=indexes.INDEX_PRODUCTS)
    assert ix2 != ix_prod_full

    # Check index is the same
    assert ix2.storage.files == existing_files

    # Change schema once
    new_schema = original_schema.copy()
    new_schema.add('test_field_111', TEXT())
    indexes.index_def_dict[indexes.INDEX_PRODUCTS] = orig_index_def[indexes.INDEX_PRODUCTS]._replace(schema=new_schema)
    del indexes.indexes[indexes.INDEX_PRODUCTS]
    ix_new = indexes.init_index(ix2.storage, one_index=indexes.INDEX_PRODUCTS)
    assert ix_new != ix2

    # Check index has been changed now
    new_files = dict(ix_new.storage.files)
    assert new_files != existing_files
    assert ix_new.schema == new_schema
    assert ix_new.schema != original_schema

    # Reopen changed index
    del indexes.indexes[indexes.INDEX_PRODUCTS]
    ix_new2 = indexes.init_index(ix_new.storage, one_index=indexes.INDEX_PRODUCTS)
    assert ix_new2 != ix_new

    # Check index is the same
    assert ix_new2.storage.files == new_files

    # Tear down
    indexes.index_def_dict.update(orig_index_def)
    del indexes.indexes[indexes.INDEX_PRODUCTS]


def test_find_multi_token_brand_mix(ix_brand_full):
    _test_find_multi_token_brand('домик в деревне', 'Домик в деревне', 'домик в деревне', '')
    _test_find_multi_token_brand('домик деревне', 'Домик в деревне', 'домик деревне', '')
    _test_find_multi_token_brand('деревне в домик', 'Домик в деревне', 'деревне в домик', '')
    _test_find_multi_token_brand('домик деревне в', 'Домик в деревне', 'домик деревне', 'в')
    _test_find_multi_token_brand('в домик деревне', 'Домик в деревне', 'домик деревне', 'в')

    _test_find_multi_token_brand_negative('домик в большой деревне')


def _test_find_multi_token_brand(q, brand, matched, not_matched):
    with oq_find.find_brands(q, group_limit=1) as rs:
        assert rs.size > 0
        for m_brand in rs.data:
            if m_brand == brand:
                assert rs.matched_tokens() == matched.split()
                assert rs.not_matched_tokens() == not_matched.split()
                break
        else:
            raise AssertionError("Cannot find brand '%s' in result set" % brand)

def _test_find_multi_token_brand_negative(q):
    with oq_find.find_brands(q) as rs:
        assert rs.size == 0

def test_find_multi_token_brand_multi_match(ix_brand_full):
    # Full exact match
    with oq_find.find_brands('молоко рузское') as rs:
        assert rs.size == 1
        assert rs.data.next() == 'Рузское молоко'
        assert rs.matched_tokens() == 'молоко рузское'.split()
        assert rs.not_matched_tokens() == ''.split()

    # Partial synonyms match
    with oq_find.find_brands('молоко пастер Рузское') as rs:
        assert rs.size > 0
        assert rs.data.next() == 'Рузское молоко'
        assert rs.matched_tokens() == 'рузское'.split()
        assert rs.not_matched_tokens() == 'молоко пастер'.split()

def test_find_multi_token_brand_start_with_prop(ix_brand_full):
    _test_find_multi_token_brand('на зубок', 'На зубок', 'на зубок', '')
    _test_find_multi_token_brand_negative('на большой зубок')
    _test_find_multi_token_brand('семечки на зубок', 'На зубок', 'на зубок', 'семечки')
    _test_find_multi_token_brand_negative('семечки зубок на')

def test_find_multi_token_brand_prefix(ix_brand_full):
    _test_find_multi_token_brand('на зуб', 'На зубок', 'на зуб', '')
    _test_find_multi_token_brand('семечки на зуб', 'На зубок', 'на зуб', 'семечки')
    _test_find_multi_token_brand('дом в деревн', 'Домик в деревне', 'дом в деревн', '')
    _test_find_multi_token_brand('молоко дом в деревн', 'Домик в деревне', 'дом в деревн', 'молоко')
    # Too Short prefix
    _test_find_multi_token_brand_negative('молоко дом в де')

def test_find_multi_token_brand_prefix_exact_match_priority(ix_brand_full):
    _test_find_multi_token_brand('мол домик в деревне', 'Домик в деревне', 'домик в деревне', 'мол')

def test_find_multi_token_brand_false_prefix(ix_brand_full):
    _test_find_multi_token_brand_negative('дер в  дерев')

def test_find_multi_token_brand_joined_with_non_separator(ix_brand_full):
    # First = assert such brand in index
    _test_find_multi_token_brand('чудо-ягода', 'Чудо-ягода', 'чудо-ягода', '')
    # Now try to find tokenized
    _test_find_multi_token_brand('чудо ягода', 'Чудо-ягода', 'чудо ягода', '')
