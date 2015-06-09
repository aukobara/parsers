# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
from collections import defaultdict, OrderedDict
import pytest
from ok.dicts import build_path, to_str, main_options
from ok.dicts.product import Product
from ok.dicts.product_type import ProductType, TYPE_TUPLE_RELATION_CONTAINS, TYPE_TUPLE_RELATION_EQUALS, \
    TYPE_TUPLE_RELATION_SUBSET_OF
from ok.dicts.product_type_dict import ProductTypeDict
from ok.settings import ensure_baseline_dir


# noinspection PyUnresolvedReferences
@pytest.fixture
def types_dict():
    pdt = ProductTypeDict()
    ProductType.reload()
    return pdt

def test_build_tag_types_from_products_new(types_dict):
    """@param ProductTypeDict types_dict: pdt"""
    p1 = Product(sqn='продукт1', tags=['таг1'])
    p2 = Product(sqn='продукт2', tags=['таг1'])
    pt1 = ProductType(p1.sqn)
    pt2 = ProductType(p2.sqn)
    pt_tag = ProductType('#таг1')
    type_tuples = defaultdict(list, {pt1: [p1.sqn], pt2: [p2.sqn]})

    types_dict.build_tag_types_from_products([p1, p2], type_tuples)

    assert pt_tag in type_tuples
    assert type_tuples[pt_tag] == [p1.sqn, p2.sqn]
    assert pt1 in pt_tag.related_types(TYPE_TUPLE_RELATION_CONTAINS)
    assert pt2 in pt_tag.related_types(TYPE_TUPLE_RELATION_CONTAINS)


def test_build_tag_types_from_products_merge(types_dict):
    """@param ProductTypeDict types_dict: pdt"""
    type_tuples = defaultdict(list)

    # Was one tagged product
    p1 = Product(sqn='продукт1', tags=['таг1'])
    pt1 = ProductType(p1.sqn)
    type_tuples[pt1] = [p1.sqn]
    # Assume pt1 already was equals to pt_tag
    pt_tag = ProductType('#таг1')
    pt1.equals_to(pt_tag)
    type_tuples[pt_tag] = [p1.sqn]

    # New type arrived
    p2 = Product(sqn='продукт2', tags=['таг1'])
    pt2 = ProductType(p2.sqn)
    type_tuples[pt2] = [p2.sqn]

    types_dict.build_tag_types_from_products([p1, p2], type_tuples)

    assert pt_tag in type_tuples
    assert set(type_tuples[pt_tag]) >= {p1.sqn, p2.sqn}
    assert pt1 in pt_tag.related_types(TYPE_TUPLE_RELATION_CONTAINS)
    assert pt2 in pt_tag.related_types(TYPE_TUPLE_RELATION_CONTAINS)


def test_build_tag_types_from_products_merge_transient(types_dict):
    """@param ProductTypeDict types_dict: pdt"""
    type_tuples = defaultdict(list)

    # Was one tagged product with two tags
    p1 = Product(sqn='продукт1', tags=['таг1', 'таг2'])
    pt1 = ProductType(p1.sqn)
    type_tuples[pt1] = [p1.sqn]
    # Assume pt1 already was equals to pt_tag
    pt_tag1 = ProductType('#таг1')
    pt1.equals_to(pt_tag1)
    type_tuples[pt_tag1] = [p1.sqn]
    pt_tag2 = ProductType('#таг2')
    pt1.equals_to(pt_tag2)
    type_tuples[pt_tag2] = [p1.sqn]
    pt_tag1.equals_to(pt_tag2)

    # New type arrived
    p2 = Product(sqn='продукт2', tags=['таг1'])
    pt2 = ProductType(p2.sqn)
    type_tuples[pt2] = [p2.sqn]

    p3 = Product(sqn='продукт3', tags=['таг2'])
    pt3 = ProductType(p3.sqn)
    type_tuples[pt3] = [p3.sqn]

    types_dict.build_tag_types_from_products([p1, p2, p3], type_tuples)

    assert pt_tag1 in type_tuples
    assert pt_tag2 in type_tuples
    assert set(type_tuples[pt_tag1]) == {p1.sqn, p2.sqn}
    assert set(type_tuples[pt_tag2]) == {p1.sqn, p3.sqn}
    # Tags are now have different product sets - no relation
    assert not pt_tag1.get_relation(pt_tag2)
    # All product types now are contained in their tag types but not equal to any other type
    assert len(pt1.relations()) == 2 and pt1.get_relation(pt_tag1).rel_type == TYPE_TUPLE_RELATION_SUBSET_OF
    assert len(pt1.relations()) == 2 and pt1.get_relation(pt_tag2).rel_type == TYPE_TUPLE_RELATION_SUBSET_OF
    assert len(pt2.relations()) == 1 and pt2.get_relation(pt_tag1).rel_type == TYPE_TUPLE_RELATION_SUBSET_OF
    assert len(pt3.relations()) == 1 and pt3.get_relation(pt_tag2).rel_type == TYPE_TUPLE_RELATION_SUBSET_OF


def test_hdiet_merge_tags_full(types_dict):
    """@param ProductTypeDict types_dict: pdt"""
    types_dict.from_json(build_path(ensure_baseline_dir(), 'product_types_hdiet.json', None))
    types_dict.min_meaningful_type_capacity = 2
    products = Product.from_meta_csv('resources/test/products_meta_test_hdiet_merge.csv')
    type_tuples = types_dict.build_from_products(products)

    pt1 = ProductType('яйцо', 'перепелиное')
    pt_tag1 = ProductType('#яйцо')

    types_to_json = OrderedDict((to_str(k), [len(set(sqns))]+[to_str(rel) for rel in k.relations()])
                        for k, sqns in sorted(type_tuples.viewitems(), key=lambda _t: to_str(_t[0])))

    relation = pt1.get_relation(pt_tag1)
    assert relation.rel_type == TYPE_TUPLE_RELATION_EQUALS
    assert to_str(relation) in types_to_json[to_str(pt1)]


def test_from_json_dont_change_full(types_dict):
    """@param ProductTypeDict types_dict: pdt"""
    config = main_options([])
    types_dict.from_json(config.product_types_in_json)

    assert len(types_dict.get_type_tuples()) > 0
    assert len(ProductType.all_cached_singletons()) == len(types_dict.get_type_tuples())

    types_dict = ProductTypeDict()
    ProductType.reload()
    types_dict.from_json(config.product_types_in_json, dont_change=True)

    assert len(types_dict.get_type_tuples()) > 0
    assert len(ProductType.all_cached_singletons()) == 0

