# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

import itertools


class RS(object):
    def __init__(self, fetcher, limit, on_close=None):
        self._size = None
        """@type: int"""
        # Generator object with sequence of data for one field (default, or one field in return_fields)
        # or tuple with multiple fields data (if multiple fields in return_fields)
        self._data = None
        self._fetcher = fetcher
        """@type: ok.query.whoosh_contrib.base.BaseFindQuery"""
        self.limit = limit
        """@type: int|None"""
        self.on_close = on_close

    def _ensure_fetched(self):
        if self._size is None:
            data = self._fetcher(limit=self.limit)
            try:
                first = next(data)
            except StopIteration:
                self._data = iter([])
                self._size = 0
            else:
                self._data = itertools.chain([first], data)
                self._size = self._fetcher.result_size

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.on_close is not None:
            self.on_close()
        self._fetcher.close()

    @property
    def size(self):
        self._ensure_fetched()
        return self._size

    @property
    def query(self):
        self._ensure_fetched()
        return self._fetcher.matched_query

    @property
    def data(self):
        self._ensure_fetched()
        return self._data

    @property
    def score(self):
        """@rtype: float"""
        self._ensure_fetched()
        return self._fetcher.current_match.score

    def facet_counts(self, facet_field):
        """@rtype: dict of (unicode, int)"""
        self._ensure_fetched()
        return self._fetcher.facet_counts(facet_field)

    def not_matched_terms(self):
        """@rtype: list[unicode]"""
        self._ensure_fetched()
        matched_terms = {t[1].lower() for t in self._fetcher.matched_terms}
        original_tokens = self._fetcher.q_tokenized.tokens
        result = []
        for token in original_tokens:
            if token not in matched_terms:
                result.append(token)
        return result


def find_products(products_query_str, limit=10, return_fields=None, facet_fields=None):
    from ok.query.whoosh_contrib import find_products

    # from whoosh import scoring
    # w_model = scoring.DebugModel()
    # searcher = ix.searcher(weighting=w_model)

    q = find_products.FindProductsQuery(products_query_str, return_fields=return_fields, facet_fields=facet_fields)

    # rs = RS(q, searcher, limit, on_close=lambda: log.debug(to_str(w_model.log)))
    return RS(q, limit)


def find_brands(brands_query_str):
    from ok.query.whoosh_contrib import find_brands

    q = find_brands.FindBrandsQuery(brands_query_str, return_fields=['brand'])
    return RS(q, limit=None)
