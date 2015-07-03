# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

from collections import defaultdict

from whoosh import query
from whoosh.analysis import RegexTokenizer, LowercaseFilter, StopFilter, StemFilter
from whoosh.columns import RefBytesColumn
from whoosh.fields import TEXT, SchemaClass, ID, KEYWORD
from whoosh.qparser.plugins import PrefixPlugin, WildcardPlugin

from whoosh.searching import Searcher
from whoosh.qparser import QueryParser, syntax

from ok.dicts.product_type import ProductType
from ok.dicts.product_type_dict import ProductTypeDict
from ok.dicts.term import TypeTerm

from ok.query.whoosh_contrib.analyze import MainFormFilter
from ok.query.whoosh_contrib.base import BaseFindQuery
from ok.query.whoosh_contrib import utils

INDEX_NAME = 'Products.idx'

class ProductsSchema(SchemaClass):
    pfqn = TEXT(stored=True,
                analyzer=RegexTokenizer() | LowercaseFilter() | StopFilter(lang='ru') |
                         MainFormFilter() | StemFilter(lang='ru', cachesize=50000)
                )
    types = KEYWORD(stored=True, field_boost=2.0, sortable=RefBytesColumn())
    brand = ID(stored=True, sortable=RefBytesColumn())
    field_serial_4 = ID()

SCHEMA = ProductsSchema()
"""@type: whoosh.fields.Schema"""

def product_type_normalizer(value):
    values = value
    if not value:
        return
    if not isinstance(value, set):
        values = {value}
    r = set()
    for pt in values:
        assert isinstance(pt, ProductType)
        text = ' + '.join(sorted(map(TypeTerm.make, pt.get_main_form_term_ids())))
        r.add(text)
    return list(r)


def feeder(writer):
    from ok.dicts import main_options
    from ok.dicts.product import Product

    config = main_options([])
    products = Product.from_meta_csv(config.products_meta_in_csvname)
    for p in products:
        writer.add_document(pfqn=p.pfqn, types=product_type_normalizer(p['types']), brand=p['brand'])
    return data_checksum()


def data_checksum():
    """@rtype: long"""
    from ok.dicts import main_options
    config = main_options([])
    return utils.text_data_file_checksum(config.products_meta_in_csvname)


class FindProductsQuery(BaseFindQuery):
    qp = QueryParser('pfqn', SCHEMA, termclass=query.Prefix, group=syntax.OrGroup)
    qp.remove_plugin_class(WildcardPlugin)
    qp.add_plugin(PrefixPlugin)
    pdt = ProductTypeDict()

    # Base attributes setup
    need_matched_terms = True
    index_name = INDEX_NAME

    def __init__(self, q, searcher=None, return_fields=None, facet_fields=None):
        """
        @param unicode q: query string
        @param Searcher|None searcher: whoosh_contrib searcher
        """
        self.q_original = q

        and_maybe_scoring_q = self.q = self.qp.parse(q)

        self.p_types = self.pdt.collect_sqn_type_tuples(q)
        len_map = defaultdict(set)
        [len_map[len(pt)].add(product_type_normalizer(pt)[0]) for pt in self.p_types]

        q_types = []
        for _, len_p_types in sorted(len_map.items(), key=lambda _l: _l[0], reverse=True):
            same_len_terms = [query.Term('types', pt_norm_str) for pt_norm_str in len_p_types]
            q_types.append(query.AndMaybe(query.And(same_len_terms), and_maybe_scoring_q))
            q_types.append(query.AndMaybe(query.Or(same_len_terms), and_maybe_scoring_q))
        # Final attempt of hope - if exact types not matched try direct pfqn query
        q_types.append(self.qp.parse(self.q_original))

        super(FindProductsQuery, self).__init__(q_types, searcher, return_fields=return_fields, facet_fields=facet_fields)
