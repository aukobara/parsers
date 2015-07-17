# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

import itertools


class RS(object):
    def __init__(self, fetcher, on_close=None):
        self._size = None
        """@type: int"""
        # Generator object with sequence of data for one field (default, or one field in return_fields)
        # or tuple with multiple fields data (if multiple fields in return_fields)
        self._data = None
        """@type: collections.Iterator[list|unicode]"""
        self._fetcher = fetcher
        """@type: ok.query.whoosh_contrib.base.BaseFindQuery"""
        self.on_close = on_close

    def _ensure_fetched(self):
        if self._size is None:
            data = self._fetcher()
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

    def matched_tokens(self):
        """@rtype: list[QueryToken]"""
        self._ensure_fetched()
        return self._fetcher.matched_tokens

    def not_matched_tokens(self):
        """@rtype: list[unicode]"""
        self._ensure_fetched()
        matched_tokens = self._fetcher.matched_tokens
        original_tokens = self._fetcher.q_tokenized.tokens
        result = []
        if matched_tokens:
            pos_list = {token.position for token in matched_tokens}
            for token in original_tokens:
                if token.position not in pos_list:
                    result.append(token)
        return result


def find_products(products_query_str, limit=10, return_fields=None, facet_fields=None):
    from ok.query.whoosh_contrib import indexes
    from ok.query.whoosh_contrib import find_products

    # from whoosh import scoring
    # w_model = scoring.DebugModel()
    # searcher = ix.searcher(weighting=w_model)

    assert find_products.FindProductsQuery in indexes.index_def_dict[indexes.INDEX_PRODUCTS].queries

    q = find_products.FindProductsQuery(products_query_str, return_fields=return_fields, facet_fields=facet_fields, limit=limit)

    # rs = RS(q, searcher, limit, on_close=lambda: log.debug(to_str(w_model.log)))
    return RS(q)


BRANDS_SORT_BY_SCORE = 'score'
BRANDS_SORT_BY_BRAND = 'brand'

def find_brands(brands_query_str, sort_by=BRANDS_SORT_BY_SCORE, group_limit=1):
    """
    Find brands in query string. Brands may have multiple synonyms contained in the query string.
    Main brand name will be returned only - one that is used in Products 'brand' field.
    Query may contain multiple entries of the same brand, different synonyms of the same brand or different brands.
    Brands terms may be in short form (prefixes) with min length 3 characters. Less than 3 characters will be treated as full term (or proposition).
    Propositions inside brand name will be ignored. Proposition at first position in brand sequence (for multi token brands) will be
    treated as regular brand's token and must be first token in matching brand name as well.
    Beside this rule all other terms inside brand token sequence may be in arbitrary order but must be a single phrase (aka zero proximity).

    Results will be returned in rank order (more relevant first) and sorted as specified in parameters.

    Sort By Score - result will consist of blocks with same score. I.e. if group_limit=1 all records will represent matched brands with max score.
    For group_limit=2 - there will be brands with 2 topmost score values and so on.

    Sort By Brand - result will consist of blocks each for the same matched brand ordered by relevancy. I.e. first group for all matched synonyms
    of top score brand, 2nd group for matched synonyms of 2nd topmost scored brand and so one. Brand score is the score of most relevant brand
    synonym.

    @param unicode|ok.query.tokens.Query brands_query_str: query string
    @param int sort_by: BRANDS_SORT_BY_SCORE or BRANDS_SORT_BY_BRAND
    @param int|None group_limit: if None all matched brand synonyms will be returned
    @rtype: RS
    """
    from ok.query.whoosh_contrib import indexes
    from ok.query.whoosh_contrib import find_brands

    assert find_brands.FindBrandsQuery in indexes.index_def_dict[indexes.INDEX_BRANDS].queries

    assert sort_by == BRANDS_SORT_BY_BRAND or sort_by == BRANDS_SORT_BY_SCORE
    q = find_brands.FindBrandsQuery(brands_query_str, return_fields=['brand'], limit=group_limit, sort_by_facet_name=sort_by)

    return RS(q)
