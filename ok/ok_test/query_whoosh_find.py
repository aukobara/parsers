# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

import logging
import pytest

import ok.query as oq

app_log = logging.getLogger('ok')
app_log.setLevel(logging.DEBUG)
app_log.addHandler(logging.StreamHandler())


@pytest.fixture(scope='module')
def ix_full():
    from whoosh.filedb.filestore import RamStorage
    from ok.query.whoosh_contrib import indexes

    st = RamStorage()
    if indexes.INDEX_PRODUCTS in indexes.indexes:
        del indexes.indexes[indexes.INDEX_PRODUCTS]
    ix = indexes.init_index(st, one_index=indexes.INDEX_PRODUCTS)
    return ix


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
        indexes.IndexDef(orig_index_def[indexes.INDEX_PRODUCTS].schema, test_feeder, lambda: 1)

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
    with oq.find_products('тест', return_fields=['pfqn']) as rs:
        assert rs.size == 1
        assert 'тест' == next(rs.data)


def test_select_one(ix_test_many):
    with oq.find_products('тест2 тест', return_fields=['pfqn']) as rs:
        assert rs.size == 1
        assert 'тест тест2' == next(rs.data)


def test_facets(ix_test_many):
    with oq.find_products('тест', return_fields=['pfqn'], facet_fields=['brand']) as rs:
        assert rs.size > 1
        assert 'тест' in rs.data
        facet_counts = rs.facet_counts('brand')
        assert facet_counts and len(facet_counts) == 2
        assert sum(facet_counts.values()) == rs.size
        assert facet_counts == {'бренд1': 2, 'бренд2': 1}

def test_find_products_full(ix_full):
    with oq.find_products('масло', return_fields=['types']) as rs:
        assert rs.size > 0
        assert all('масло' in types for types in rs.data)
