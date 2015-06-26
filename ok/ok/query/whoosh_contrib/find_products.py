# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
from collections import defaultdict
from whoosh import query
from whoosh.analysis import Filter, RegexTokenizer, LowercaseFilter, StopFilter, StemFilter

from whoosh.fields import TEXT, SchemaClass, ID, KEYWORD
from whoosh.qparser.plugins import PrefixPlugin
from whoosh.searching import Searcher
from whoosh.qparser import QueryParser, syntax
from ok.dicts.product_type import ProductType
from ok.dicts.product_type_dict import ProductTypeDict
from ok.dicts.term import TypeTerm

INDEX_NAME = 'Products.idx'

class MainFormFilter(Filter):
    is_morph = True

    def __call__(self, tokens):
        context = []
        for t in tokens:
            yield t
            if not t.stopped:
                text = t.text
                term = TypeTerm.term_dict.get_by_unicode(text)
                if term:
                    context.append(term)

        for term in context:
            wf = term.word_forms(context=context, fail_on_context=False)
            for term_form in wf or []:
                if term_form not in context:
                    t.text = term_form
                    yield t

def product_type_normalizer(value):
    values = value
    if not value:
        return
    if not isinstance(value, set):
        values = {value}
    r = []
    for pt in values:
        assert isinstance(pt, ProductType)
        text = ' + '.join(sorted(map(TypeTerm.make, pt.get_main_form_term_ids())))
        r.append(text)
    return r

class ProductsSchema(SchemaClass):
    pfqn = TEXT(stored=True,
                analyzer= RegexTokenizer() | LowercaseFilter() | StopFilter(lang='ru') |
                          MainFormFilter() | StemFilter(lang='ru', cachesize=50000)
                )
    types = KEYWORD(scorable=True, field_boost=2.0)
    field_serial_0 = ID()

SCHEMA = ProductsSchema()

def feeder(writer):
    from ok.dicts import main_options
    from ok.dicts.product import Product

    config = main_options([])
    products = Product.from_meta_csv(config.products_meta_in_csvname)
    for p in products:
        writer.add_document(pfqn=p.pfqn, types=product_type_normalizer(p['types']))
    return data_checksum()

def data_checksum():
    """@rtype: long"""
    from ok.dicts import main_options
    config = main_options([])

    from ..whoosh_contrib import text_data_file_checksum
    return text_data_file_checksum(config.products_meta_in_csvname)

class FindProductsQuery(object):
    qp = QueryParser('pfqn', SCHEMA, termclass=query.Prefix, group=syntax.OrGroup)
    qp.add_plugin(PrefixPlugin)
    pdt = ProductTypeDict()

    def __init__(self, q, searcher):
        """
        @param unicode q: query string
        @param Searcher searcher: whoosh_contrib searcher
        """
        self.q_original = q
        self.q = self.qp.parse(q)
        self.p_types = self.pdt.collect_sqn_type_tuples(q)
        len_map = defaultdict(set)
        [len_map[len(pt)].add(product_type_normalizer(pt)[0]) for pt in self.p_types]

        q_types = []
        for _, len_p_types in sorted(len_map.items(), key=lambda _l:_l[0], reverse=True):
            same_len_terms = [query.Term('types', pt_norm_str) for pt_norm_str in len_p_types]
            q_types.append(query.And(same_len_terms))
            q_types.append(query.Or(same_len_terms))
        self.q_types = q_types

        self.searcher = searcher
        self.result_size = None
        self.matched_query = None

    def __call__(self, limit=10):
        match_found = False
        for q_type in self.q_types:
            q_attempt = query.AndMaybe(q_type, self.q) if self.q else q_type
            r = self.searcher.search(q_attempt, limit=limit)
            for match in r:
                match_found = True
                if self.result_size is None:
                    self.result_size = len(r) if r.has_exact_length() else r.estimated_min_length()
                if self.matched_query is None:
                    self.matched_query = q_attempt
                pfqn = match['pfqn']
                yield pfqn
            if match_found:
                break
        if not match_found:
            # Try direct pfqn query
            self.q_types = [self.qp.parse(self.q_original)]
            self.q = None
            for pfqn in self(limit=limit):
                yield pfqn


