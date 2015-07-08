# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

from whoosh.fields import Schema, TEXT, ID
from whoosh import query as whoosh_query
from ok.query import parse_query

from ok.query.whoosh_contrib.base import BaseFindQuery

INDEX_NAME = 'Brands.idx'
SCHEMA = Schema(brand=TEXT(stored=True), serial_2=ID())


def feeder(writer):
    from ok.dicts import main_options
    from ok.dicts.brand import Brand

    config = main_options([])
    Brand.from_csv(config.brands_in_csvname)
    for brand in Brand.all(skip_no_brand=True):
        for brand_name in [brand.name] + brand.synonyms:
            writer.add_document(brand=[brand_name.lower()], _stored_brand=brand_name)


class FindBrandsQuery(BaseFindQuery):
    index_name = INDEX_NAME
    need_matched_terms = True

    def query_variants(self):
        tokens = self.q_tokenized.tokens
        term_queries = []
        seen = set()
        for token in tokens:
            if token not in seen and self.is_term_in_index('brand', token):
                term_queries.append(whoosh_query.Term('brand', token))
                seen.add(token)

        queries = []
        if term_queries:
            queries.append(whoosh_query.And(term_queries))
            if len(term_queries) > 1:
                queries.append(whoosh_query.Or(term_queries))
        return queries

    def __call__(self, limit=10):
        data = super(FindBrandsQuery, self).__call__(limit)
        original_query_tokens = self.q_tokenized
        for rv in data:
            current_match = self.current_match
            brand = current_match['brand']
            brand_tokens = parse_query(brand).tokens
            # Ignore brand match - all brand terms must be present in query
            # TODO: use index terms or vector instead of parsing brand tokens each time
            if all(token in original_query_tokens for token in brand_tokens):
                yield rv

