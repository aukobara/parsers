# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

from whoosh.fields import Schema, TEXT, KEYWORD
from whoosh.searching import Searcher
from whoosh.qparser import QueryParser
from ok.dicts.brand import Brand

INDEX_NAME = 'Brands.idx'
SCHEMA = Schema(brand=KEYWORD(stored=True))

def feeder(writer):
    from ok.dicts import main_options
    from ok.dicts.brand import Brand

    config = main_options([])
    Brand.from_csv(config.brands_in_csvname)
    for brand in Brand.all(skip_no_brand=True):
        writer.add_document(brand=brand.name)

class FindBrandsQuery(object):
    qp = QueryParser('brand', SCHEMA)

    def __init__(self, q, searcher):
        """
        @param unicode q: query string
        @param Searcher searcher: whoosh_contrib searcher
        """
        self.q = self.qp.parse(q)
        self.searcher = searcher

    def __call__(self, limit=10):
        r = self.searcher.search(self.q, limit=limit)
        for match in r:
            brand = match['brand']
            yield brand
