# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

from collections import defaultdict

from whoosh import query
from whoosh.analysis import RegexTokenizer, LowercaseFilter, StopFilter, StemFilter
from whoosh.columns import RefBytesColumn
from whoosh.fields import TEXT, SchemaClass, ID, KEYWORD
from whoosh.qparser.plugins import PrefixPlugin, WildcardPlugin
from whoosh.qparser import QueryParser, syntax
from ok.utils import to_str

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
    weight = ID()
    pack = ID()
    fat = ID()
    field_serial_15 = ID()

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
    products = products_data_source()
    for p in products:
        feed_product(p, writer)
    return data_checksum()


def products_data_source():
    from ok.dicts import main_options
    from ok.dicts.product import Product

    config = main_options([])
    return Product.from_meta_csv(config.products_meta_in_csvname)


def feed_product(p, writer):
    pq = ProductQuery.from_product(p)
    # TODO: make test to validate only simple text types are passed to writer as field terms
    # whoosh will serialize terms and on next run their can be a problems with deserialized terms
    writer.add_document(pfqn=pq.pfqn, types=product_type_normalizer(pq.types), tail=map(to_str, pq.tail), brand=pq.brand,
                        fat=list(pq.fat_all), pack=list(pq.pack_all), weight=list(pq.weight_all))


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

    @staticmethod
    def _tokenize_query(q):
        from ok.query.product import ProductQueryParser
        return ProductQueryParser(q)

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
        and_maybe_scoring_q = self.tail_qp.parse(to_str(self.q_original))

        wfp_term_queries = self.supplementary_queries(pq)

        len_map = defaultdict(set)
        [len_map[len(pt)].add(p_type_cache[pt]) for pt in pq.types]

        def get_query(term_group=None):
            if wfp_term_queries:
                if len(wfp_term_queries) == 1:
                    wpf_group_queries = [wfp_term_queries[0]]
                else:
                    wpf_group_queries = [query.And(wfp_term_queries), query.Or(wfp_term_queries)]
                for wpf_gq in wpf_group_queries:
                    yield query.AndMaybe(term_group & wpf_gq if term_group else wpf_gq, and_maybe_scoring_q)
            if term_group:
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
            q_types.extend(get_query())

        # Final attempt of hope - if exact types not matched try direct pfqn query
        q_types.append(self.qp.parse(to_str(self.q_original)))
        return q_types

    def supplementary_queries(self, pq):
        """@param ok.query.product.ProductQuery pq: parsed query"""
        supp_fields = ['weight', 'fat', 'pack', 'brand']
        wfp_term_queries = []
        for field in supp_fields:
            if field in pq:
                term_set = pq['%s_all' % field]
                if len(term_set) == 1:
                    wfp_term_queries.append(query.Term(field, next(iter(term_set))))
                else:
                    wfp_term_queries.append(query.Or(map(lambda term: query.Term(field, term), term_set)))

        return wfp_term_queries
