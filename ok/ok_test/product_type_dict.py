# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
from collections import defaultdict, OrderedDict
import pytest
from ok.dicts import build_path, to_str, main_options
from ok.dicts.product import Product
from ok.dicts.product_type import ProductType, TYPE_TUPLE_RELATION_CONTAINS, TYPE_TUPLE_RELATION_EQUALS, \
    TYPE_TUPLE_RELATION_SUBSET_OF, TYPE_TUPLE_RELATION_ALMOST
from ok.dicts.product_type_dict import ProductTypeDict, reload_product_type_dict
from ok.dicts.term import load_term_dict, TypeTerm
from ok.settings import ensure_baseline_dir

TEST_RESOURCES_DIR = 'resources/test'

# noinspection PyUnresolvedReferences
@pytest.fixture
def types_dict():
    pdt = ProductTypeDict()
    pdt.VERBOSE = True
    ProductType.reload()
    return pdt

# noinspection PyUnresolvedReferences
@pytest.fixture(scope='module')
def types_dict_full_common():
    load_term_dict()
    pdt = reload_product_type_dict()
    return pdt

# noinspection PyUnresolvedReferences
@pytest.fixture
def types_dict_test_data():
    pdt = types_dict()
    pdt.from_json(build_path(TEST_RESOURCES_DIR, 'product_types_test_mar.json', None))
    TypeTerm.term_dict.update_dawg()
    assert pdt.get_type_tuples()
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


def test_build_tag_types_from_products_merge_propagation(types_dict):
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
    # After 'almost' relation was introduced - Tags are in soft 'almost' relation because
    # share one sqn of two they have each. Thus, relation attribute is 50%
    assert pt_tag1.get_relation(pt_tag2).rel_type == TYPE_TUPLE_RELATION_ALMOST
    assert pt_tag1.get_relation(pt_tag2).rel_attr == 0.5
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


def test_from_json_dont_change(types_dict_test_data):
    """@param ProductTypeDict types_dict: types_dict_test_data"""
    assert len(ProductType.all_cached_singletons()) == len(types_dict_test_data.get_type_tuples())

    new_types_dict = ProductTypeDict()
    ProductType.reload()
    new_types_dict.from_json(build_path(TEST_RESOURCES_DIR, 'product_types_test_mar.json', None), dont_change=True)

    assert len(new_types_dict.get_type_tuples()) > 0
    assert len(ProductType.all_cached_singletons()) == 0


def test_to_from_json(types_dict, tmpdir):
    """
    @param ProductTypeDict types_dict: types_dict
    @param LocalPath tmpdir: pytest temp dir
    """
    p1 = ProductType('тест1')
    p2 = ProductType('тест2')
    p3 = ProductType('тест3')
    p3.contains(p2)
    p3.contains(p1)
    p2.contains(p1)
    types_dict._type_tuples[p1] = [1]
    types_dict._type_tuples[p2] = [1]
    types_dict._type_tuples[p3] = [1]
    filename = str(tmpdir.join('test_types_dict.json'))
    types_dict.to_json(json_filename=filename)
    loaded = types_dict.from_json(json_filename=filename, dont_change=True)
    assert loaded.viewkeys() == {p1, p2, p3}
    # loaded_rel_count = sum(map(len, (l_type.relations() for l_type in loaded)))
    # assert loaded_rel_count == 6
    l1, l2, l3 = sorted(loaded, key=to_str)
    assert l3.related_types(TYPE_TUPLE_RELATION_CONTAINS) == [l1, l2]
    assert l2.related_types(TYPE_TUPLE_RELATION_CONTAINS) == [l1]
    assert l2.related_types(TYPE_TUPLE_RELATION_SUBSET_OF) == [l3]
    assert l1.related_types(TYPE_TUPLE_RELATION_SUBSET_OF) == [l2, l3]
    # Check there is no other relations than asserted above
    assert l3.relations() == l3.relations(TYPE_TUPLE_RELATION_CONTAINS)
    assert l2.relations() == l2.relations(TYPE_TUPLE_RELATION_CONTAINS) + l2.relations(TYPE_TUPLE_RELATION_SUBSET_OF)
    assert l1.relations() == l1.relations(TYPE_TUPLE_RELATION_SUBSET_OF)


def test_to_json_only_meaningful(types_dict):
    """
    @param ProductTypeDict types_dict: types_dict
    @param LocalPath tmpdir: pytest temp dir
    """
    types_dict.min_meaningful_type_capacity = 2
    p1 = ProductType('тест1')
    p2 = ProductType('тест1', 'тест2', meaningful=True)
    p3 = ProductType('тест1', 'тест2', 'тест3')
    p1.contains(p2)
    p1.contains(p3)
    p2.contains(p3)
    types_dict._type_tuples[p1] = [1]
    types_dict._type_tuples[p2] = [1]
    types_dict._type_tuples[p3] = [1]

    json_types = types_dict._get_json_repr_dict()
    assert json_types.viewkeys() == {p1, p2}
    assert json_types[p1][1:] == [p1.get_relation(p2)]
    assert json_types[p2][1:] == [p2.get_relation(p1)]


def test_from_bin_json(types_dict_test_data, tmpdir):
    """
    @param ProductTypeDict types_dict_test_data: types_dict
    @param LocalPath tmpdir: pytest temp dir
    """
    pdt = types_dict_test_data
    old_types = sorted(pdt.get_type_tuples().keys())
    assert old_types

    filename = str(tmpdir.join('test_types_dict.bin.json'))
    pdt.to_bin_json(json_filename=filename)

    pdt_new = ProductTypeDict()
    pdt_new.VERBOSE = True
    pdt_new.from_json(filename, dont_change=True, pure_json=True, binary_format=True)

    new_types = sorted(pdt_new.get_type_tuples().keys())
    assert old_types == new_types
    for i in range(len(old_types)):
        assert len(old_types[i].relations()) == len(new_types[i].relations())
        assert old_types[i].relations() == new_types[i].relations()


def test_from_bin_json_full(types_dict_full_common, tmpdir):
    test_from_bin_json(types_dict_full_common, tmpdir)
