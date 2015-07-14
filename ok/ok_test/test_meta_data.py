# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
from collections import defaultdict
import itertools

import pytest

from ok.dicts.brand import Brand
from ok.dicts.product_type import ProductType
from ok.dicts.term import TypeTerm


@pytest.fixture(scope='module')
def config():
    """@rtype: ok.dicts.conf_type"""
    from ok.dicts import main_options
    return main_options([])


@pytest.fixture(scope='module')
def brands(config):
    """@param ok.dicts.conf_type config: config"""
    Brand.from_csv(config.brands_in_csvname)
    return Brand


@pytest.fixture(scope='module')
def terms(config):
    """@param ok.dicts.conf_type config: config"""
    from ok.dicts.term import load_term_dict
    return load_term_dict(config.term_dict)


@pytest.fixture(scope='module')
def ptypes(config, terms):
    """@param ok.dicts.conf_type config: config"""
    from ok.dicts.product_type_dict import reload_product_type_dict
    ptd = reload_product_type_dict(config)
    return ptd


def test_brand_has_no_product_type_synonyms_full(brands, ptypes):
    """
    @param ok.dicts.brand.Brand brands: Brand class with static data
    @param ok.dicts.product_type_dict.ProductTypeDict: product types
    """
    known_type_term_set = ptypes.get_type_term_set()
    bad_brands = defaultdict(set)
    susp_brands = defaultdict(set)
    print('test_brand_has_no_product_type_synonyms: Brands testing', end='')
    for brand in brands.all(skip_no_brand=True):
        for brand_term_str in [brand.name] + brand.synonyms:
            brand_terms = set(TypeTerm.parse_term_string(brand_term_str))
            if brand_terms.issubset(known_type_term_set):
                susp_brands[brand_term_str].add(brand)
                # Check only brands with all known type terms. If brand name has unique term it will not be confused with product type
                for bt_combo in itertools.permutations(brand_terms, len(brand_terms)):
                    pt = ProductType(*bt_combo, singleton=False)
                    try:
                        assert pt not in ptypes
                    except AssertionError:
                        bad_brands[brand_term_str].add(brand)
    else:
        print()
        print('Finished for %d brands' % len(brands.all()))
        print("Found %d brands with all terms known product types but not types directly:" % len(susp_brands))
        for brand_term_str, brand in susp_brands.viewitems():
            print('%s: "%s"' % (brand_term_str, '", "'.join(map(lambda b: b.name, brand))))

    if len(bad_brands) > 0:
        print()
        print("=" * 20, " BAD BRANDS:")
        for brand_term_str, brand in bad_brands.viewitems():
            print("Brand term string '%s' may be confused with product types. Brand: '%s'" % (brand_term_str, '", "'.join(map(lambda b: b.name, brand))))
        raise AssertionError("Found %d brands with names/synonyms identical to product types" % len(bad_brands))

if __name__ == '__main__':
    _config = config()
    _terms = terms(_config)
    _brands = brands(_config)
    _ptypes = ptypes(_config, _terms)
    test_brand_has_no_product_type_synonyms_full(_brands, _ptypes)
