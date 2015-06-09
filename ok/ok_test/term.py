# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
import pytest

import ok.dicts
from ok.dicts.product_type import ProductType
from ok.dicts.product_type_dict import reload_product_type_dict
from ok.dicts.term import load_term_dict, TypeTerm, ContextRequiredTypeTermException, dump_term_dict_from_product_types, \
    CompoundTypeTerm


# noinspection PyUnresolvedReferences
@pytest.fixture(autouse=True)
def clear_terms_dict():
    TypeTerm.term_dict.clear()

# noinspection PyUnresolvedReferences
@pytest.fixture
def pdt():
    config = ok.dicts.main_options(
        ['test.py', '-base-dir', 'resources\\test', '-in-product-types-json', 'product_types_test_mar.json'])
    _pdt = reload_product_type_dict(config)
    return _pdt

# noinspection PyUnresolvedReferences
@pytest.fixture
def pdt_full():
    # TODO: rewrite to parametrized fixture
    _pdt = reload_product_type_dict(config=None)
    return _pdt


def test_context_terms_find_compound(pdt):
    rel = pdt.find_product_type_relations(u'продукт йогуртный перс/мар/ананас/дыня')

    _assert_prod_mar_types(rel)

    pt_mar = ProductType(u'продукт', u'йогуртный', u'мар')
    pt_mar_full = ProductType(u'продукт', u'йогуртный', u'маракуйя')
    eq_relation = pt_mar.equals_to(pt_mar_full, dont_change=True)
    assert eq_relation in rel[pt_mar]

    # Only in test data
    pt_mar_bad = ProductType(u'продукт', u'мар')
    subset_of_relation = pt_mar.subset_of(pt_mar_bad, dont_change=True)
    assert subset_of_relation in rel[pt_mar]


def test_context_terms_parse_compound(pdt):
    types = pdt.collect_sqn_type_tuples(u'продукт йогуртный перс/мар/ананас/дыня')
    _assert_prod_mar_types(types)


def test_context_terms_main_form_with_compatible_compound(pdt):
    term_comp = TypeTerm.make('продукт-йогуртный')
    term_context_req = TypeTerm.make('мар')
    context = [term_comp, term_context_req]

    term_main = term_context_req.get_main_form(context=context)
    assert term_main == 'маракуйя'

def test_context_terms_compound_main_form_with_compatible_compound(pdt):
    term_comp = TypeTerm.make('продукт-йогуртный')
    term_context_req = TypeTerm.make('перс/мар/ананас/дыня')
    context = [term_comp, term_context_req]

    assert isinstance(term_comp, CompoundTypeTerm)
    term_main = term_context_req.get_main_form(context=context)
    assert term_main == 'перс/мар/ананас/дыня'
    assert isinstance(term_context_req, CompoundTypeTerm)
    sub_term_context_req = term_context_req.simple_sub_terms[1]
    assert sub_term_context_req == 'мар'
    with pytest.raises(ContextRequiredTypeTermException):
        sub_term_context_req.get_main_form()
    sub_term_main = sub_term_context_req.get_main_form(context)
    assert sub_term_main == 'маракуйя'


def test_context_terms_parse_with_compatible_compound(pdt):
    types = pdt.collect_sqn_type_tuples(u'продукт-йогуртный перс/мар/ананас/дыня')
    _assert_prod_mar_types(types)


def _assert_prod_mar_types(types):
    """@param set[ProductType]|list[ProductType]|dict of (ProductType, Any) types: container of ProductTypes"""
    for t in types:
        try:
            list(t.get_main_form_term_ids())
        except ContextRequiredTypeTermException:
            print("Test failed: All types after parse must be in terminal context")
            raise

    pt_mar = ProductType(u'продукт', u'йогуртный', u'мар')
    pt_mar_bad = ProductType(u'продукт', u'мар')
    pt_mar_not_context = ProductType(u'продукт', u'маракуйя')
    pt_mar_full = ProductType(u'продукт', u'йогуртный', u'маракуйя')

    assert pt_mar_bad not in types
    assert pt_mar in types
    assert pt_mar_full in types
    assert pt_mar_not_context in types


def test_context_terms_parse_compound_proposition(pdt):
    types = pdt.collect_sqn_type_tuples(u'продукт йогуртный с мар')

    _assert_prod_mar_types(types)

    pt_mar_bad = ProductType(u'продукт', u'с мар')
    pt_mar_prop = ProductType(u'продукт', u'йогуртный', u'с мар')

    assert pt_mar_bad not in types
    assert pt_mar_prop in types


def test_context_terms_full(pdt_full):
    rel = pdt_full.find_product_type_relations(u'продукт йогуртный перс/мар/ананас/дыня')

    pt_mar_bad_parent = ProductType(u'продукт', u'мар')
    pt_mar = ProductType(u'продукт', u'йогуртный', u'мар')
    pt_mar_full = ProductType(u'продукт', u'йогуртный', u'маракуйя')
    eq_relation = pt_mar.equals_to(pt_mar_full, dont_change=True)

    assert pt_mar in rel
    assert pt_mar_bad_parent not in rel
    assert eq_relation in rel[pt_mar]


def test_dawg_persistence_full():
    print("test_dawg_persistence()")
    filename = 'out/_term_dict_test.dawg'
    test_term_dict_saved = dump_term_dict_from_product_types(filename)
    test_term_dict_loaded = load_term_dict(filename)
    max_id = test_term_dict_loaded.get_max_id()
    assert test_term_dict_saved.get_max_id() == max_id and max_id > 0, "Saved and loaded dawgs are different size!"
    for i in range(1, max_id + 1):
        term_saved = test_term_dict_saved.get_by_id(i)
        term_loaded = test_term_dict_loaded.get_by_id(i)
        assert isinstance(term_saved, TypeTerm) and isinstance(term_loaded, TypeTerm), \
            "Terms have bad type"
        assert term_saved == term_loaded and type(term_saved) == type(term_loaded), \
            "Saved and Loaded terms are different!"
    print("test_dawg_persistence(): success")
