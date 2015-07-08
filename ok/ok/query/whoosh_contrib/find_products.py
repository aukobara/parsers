# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

from collections import defaultdict

from whoosh import query
from whoosh.analysis import RegexTokenizer, LowercaseFilter, StopFilter, StemFilter
from whoosh.columns import RefBytesColumn
from whoosh.fields import TEXT, SchemaClass, ID, KEYWORD
from whoosh.qparser.plugins import PrefixPlugin, WildcardPlugin
from whoosh.qparser import QueryParser, syntax

from ok.dicts.product_type import ProductType
from ok.dicts.term import TypeTerm
from ok.query.product import ProductQuery

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
    tail = TEXT(stored=True,
                analyzer=RegexTokenizer() | LowercaseFilter() | StopFilter(lang='ru') |
                         MainFormFilter() | StemFilter(lang='ru', cachesize=50000)
                )
    brand = ID(stored=True, sortable=RefBytesColumn())
    weight = ID(analyzer=RegexTokenizer(expression=r'\s\+\s', gaps=True) | LowercaseFilter())
    pack = ID(analyzer=RegexTokenizer(expression=r'\s\+\s', gaps=True) | LowercaseFilter())
    fat = ID(analyzer=RegexTokenizer(expression=r'\s\+\s', gaps=True) | LowercaseFilter())
    field_serial_10 = ID()

SCHEMA = ProductsSchema()
"""@type: whoosh.fields.Schema"""


def product_type_normalizer(value):
    """@rtype: list[unicode]"""
    values = value
    if not value:
        return None
    if isinstance(value, ProductType):
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
        feed_product(p, writer)
    return data_checksum()


def feed_product(p, writer):
    pq = ProductQuery.from_product(p)
    writer.add_document(pfqn=pq.pfqn, types=product_type_normalizer(pq.types), tail=pq.tail, brand=pq.brand,
                        fat=pq.fat, pack=pq.pack, weight=pq.weight)


def data_checksum():
    """@rtype: long"""
    from ok.dicts import main_options
    config = main_options([])
    return utils.text_data_file_checksum(config.products_meta_in_csvname)


class FindProductsQuery(BaseFindQuery):
    qp = QueryParser('pfqn', SCHEMA, termclass=query.Prefix, group=syntax.AndGroup)
    qp.remove_plugin_class(WildcardPlugin)
    qp.add_plugin(PrefixPlugin)

    tail_qp = QueryParser('tail', SCHEMA, plugins=[PrefixPlugin], termclass=query.Prefix, group=syntax.OrGroup)

    # Base attributes setup
    need_matched_terms = True
    index_name = INDEX_NAME

    p_type_cache = None

    @property
    def q_tokenized(self):
        """@rtype: ProductQueryParser"""

        q_tokenized = self._q_tokenized
        if q_tokenized is None:
            from ok.query.product import ProductQueryParser
            q_tokenized = self._q_tokenized = ProductQueryParser(self.q_original)

        return q_tokenized

    def query_variants(self):
        p_type_cache = {}

        def type_filter(p_types):
            if not p_types:
                return
            for p_type in p_types:
                type_term = product_type_normalizer(p_type)[0]
                p_type_cache[p_type] = type_term
                if self.is_term_in_index('types', type_term):
                    yield p_type

        pq = ProductQuery.from_pfqn(self.q_tokenized, type_filter=type_filter)
        and_maybe_scoring_q = self.tail_qp.parse(self.q_original)

        supp_fields = ['weight', 'fat', 'pack', 'brand']
        wfp_term_queries = []
        [wfp_term_queries.append(query.Term(sf, pq[sf])) for sf in supp_fields if pq.get(sf)]

        len_map = defaultdict(set)
        [len_map[len(pt)].add(p_type_cache[pt]) for pt in pq.types]

        def get_query(term_group):
            if wfp_term_queries:
                yield query.AndMaybe(term_group & query.And(wfp_term_queries), and_maybe_scoring_q)
                if len(wfp_term_queries) > 1:
                    yield query.AndMaybe(term_group & query.Or(wfp_term_queries), and_maybe_scoring_q)
            yield query.AndMaybe(term_group, and_maybe_scoring_q)

        q_types = []
        for _, len_p_types in sorted(len_map.items(), key=lambda _l: _l[0], reverse=True):
            same_len_terms = [query.Term('types', pt_norm_str) for pt_norm_str in len_p_types]
            q_types.extend(get_query(query.And(same_len_terms)))
            if len(same_len_terms) > 1:
                q_types.extend(get_query(query.Or(same_len_terms)))
        if not q_types and wfp_term_queries:
            # Weird situation when no types but other attributes are present
            # It can be used for listing of all brand products
            q_types.extend(get_query(query.Every('types')))

        # Final attempt of hope - if exact types not matched try direct pfqn query
        q_types.append(self.qp.parse(self.q_original))
        return q_types
