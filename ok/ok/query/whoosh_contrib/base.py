# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

from whoosh import sorting


class BaseFindQuery(object):
    # Class attributes to override
    need_matched_terms = False
    index_name = None

    def __init__(self, query_variants, searcher=None, return_fields=None, facet_fields=None):
        """
        @param list[qcore.Query] query_variants: query string
        @param whoosh.searching.Searcher searcher: whoosh_contrib searcher
        """
        self.query_variants = query_variants

        self._searcher = searcher

        self.result_size = None
        self.matched_query = None
        self.return_fields = return_fields

        self.facets = None if not facet_fields else \
            sorting.Facets({facet: sorting.FieldFacet(facet, allow_overlap=False, maptype=sorting.Count) for facet in facet_fields})

        # Accessor helper to current match document
        self._match = None
        """@type: whoosh.searching.Hit"""
        self._results = None
        """@type: whoosh.searching.Results"""

    def __call__(self, limit=10):
        searcher = self.searcher
        match_found = False
        return_one_field = return_all = None
        return_fields = self.return_fields

        for q_attempt in self.query_variants:
            r = searcher.search(q_attempt, limit=limit, terms=self.need_matched_terms, groupedby=self.facets)
            for match in r:

                if not match_found:
                    # First result found. Init result set fields
                    return_one_field = return_fields[0] if return_fields is not None and len(return_fields) == 1 else None
                    return_all = return_fields is None or return_fields == match.keys()
                if self.result_size is None:
                    self.result_size = r.estimated_min_length()
                if self.matched_query is None:
                    self.matched_query = q_attempt
                self._match = match
                self._results = r
                match_found = True

                if return_one_field:
                    yield match[return_one_field]
                elif return_all:
                    yield match.values()
                else:
                    yield map(match.get, return_fields)

            if match_found:
                self._match = None
                break

    # Current match object accessor helpers
    @property
    def current_match(self):
        return self._match

    def facet_counts(self, facet_field):
        return self._results.groups(facet_field)

    @property
    def searcher(self):
        searcher = self._searcher
        if searcher is None:
            from ok.query.whoosh_contrib import indexes
            searcher = self._searcher = indexes.searcher(self.index_name)
        return searcher

    def close(self):
        searcher = self._searcher
        if searcher is not None and not searcher.is_closed:
            searcher.close()
