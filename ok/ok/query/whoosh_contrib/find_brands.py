# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

from whoosh.fields import Schema, KEYWORD
from whoosh.searching import Searcher
from whoosh.qparser import QueryParser

from ok.query.whoosh_contrib.base import BaseFindQuery

INDEX_NAME = 'Brands.idx'
SCHEMA = Schema(brand=KEYWORD(stored=True))


def feeder(writer):
    from ok.dicts import main_options
    from ok.dicts.brand import Brand

    config = main_options([])
    Brand.from_csv(config.brands_in_csvname)
    for brand in Brand.all(skip_no_brand=True):
        writer.add_document(brand=brand.name)


class FindBrandsQuery(BaseFindQuery):
    qp = QueryParser('brand', SCHEMA)

    index_name = INDEX_NAME

    def __init__(self, q, searcher=None):
        """
        @param unicode q: query string
        @param Searcher searcher: whoosh_contrib searcher
        """
        query = self.qp.parse(q)
        super(FindBrandsQuery, self).__init__([query], searcher, return_fields=['brand'])
