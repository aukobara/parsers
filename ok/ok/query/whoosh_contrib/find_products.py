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
    from ok.dicts.term import load_term_dict
    load_term_dict()

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

    term_dict_cs = TypeTerm.term_dict.dawg_checksum_in_file(config.term_dict)
    products_cs = utils.text_data_file_checksum(config.products_meta_in_csvname)
    return products_cs + term_dict_cs


class FindProductsQuery(BaseFindQuery):
    # Base attributes setup
    need_matched_terms = True
    index_name = INDEX_NAME
    schema = SCHEMA

    qp = QueryParser('pfqn', schema, termclass=query.Prefix, group=syntax.AndGroup)
    qp.remove_plugin_class(WildcardPlugin)
    qp.add_plugin(PrefixPlugin)

    tail_qp = QueryParser('tail', schema, plugins=[PrefixPlugin], termclass=query.Prefix, group=syntax.OrGroup)

    p_type_cache = None

    @staticmethod
    def _tokenize_query(q):
        from ok.query.product import ProductQueryParser
        return ProductQueryParser(q)

    def query_variants(self):
        # TODO: extend original query with main forms of each token. Original tokens should have more boost
        original_query_string = to_str(self.q_original)
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

        scoring_query = self.tail_qp.parse(original_query_string)

        wfp_term_queries = self.supplementary_queries(pq)
        wpf_group_queries = utils.and_or_query(wfp_term_queries, And=None)

        def add_supplementary_queries(term_group=None):
            for wpf_gq in wpf_group_queries:
                # yield query.AndMaybe(term_group & wpf_gq if term_group else wpf_gq, scoring_query)
                if term_group:
                    yield query.AndMaybe(term_group, wpf_gq | scoring_query)
                else:
                    yield query.AndMaybe(wpf_gq, scoring_query)
            if term_group and not wpf_group_queries:
                yield query.AndMaybe(term_group, scoring_query)

        # Group product types by type length to allow find queries with type length priority
        len_map = defaultdict(set)
        for pt in pq.types:
            norm_type = p_type_cache[pt]
            len_map[len(pt)].add(norm_type)

        result_queries = []
        for types_length in sorted(len_map, reverse=True):
            query_terms = []
            for norm_type in len_map[types_length]:
                query_terms.append(query.Term('types', norm_type))

            for type_query in utils.and_or_query(query_terms):
                result_queries += add_supplementary_queries(type_query)

        if not result_queries and wfp_term_queries:
            # Weird situation when no types but other attributes are present
            # It can be used for listing of all brand products
            result_queries += add_supplementary_queries()

        # Final attempt of hope - if exact types not matched try direct pfqn query
        result_queries.append(self.qp.parse(original_query_string))

        return result_queries

    @staticmethod
    def supplementary_queries(pq):
        """@param ok.query.product.ProductQuery pq: parsed query"""
        supp_fields = ['weight', 'fat', 'pack', 'brand']
        wfp_term_queries = []
        for field in supp_fields:
            if field in pq:
                term_set = pq['%s_all' % field]
                wfp_term_queries += utils.and_or_query(map(lambda term: query.Term(field, term), term_set),
                                                       And=None, boost=1.5)

        return wfp_term_queries
