# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

from whoosh import sorting


class BaseFindQuery(object):
    # Class attributes to override
    need_matched_terms = False
    index_name = None
    searcher_factory = None

    def __init__(self, q, searcher=None, return_fields=None, facet_fields=None):
        """
        @param whoosh.searching.Searcher searcher: whoosh_contrib searcher
        """
        self.q_original = q
        self._q_tokenized = None

        self._searcher = searcher
        """@type: whoosh.searching.Searcher"""

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

    @property
    def q_tokenized(self):
        q_tokenized = self._q_tokenized
        if q_tokenized is None:
            from ok.query import parse_query
            q_tokenized = self._q_tokenized = parse_query(self.q_original)
        return q_tokenized

    def query_variants(self):
        raise NotImplementedError

    def __call__(self, limit=10):
        searcher = self.searcher
        match_found = False
        return_one_field = return_all = None
        return_fields = self.return_fields

        q_attempt = None
        for q_attempt in self.query_variants():
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

        # For last generator iteration keep last attempted query.
        # It can be useful for analysis of empty result
        self.matched_query = q_attempt

    # Current match object accessor helpers
    @property
    def current_match(self):
        return self._match

    @property
    def matched_terms(self):
        """
        @rtype: list[tuple[unicode]]
        @return: list of tuples (field_name, term_value)
        """
        assert self.need_matched_terms, "Query class %r must set 'need_matched_terms' to access matched terms data" % self.__class__
        return [(t[0], t[1].decode('utf-8')) for t in self.current_match.matched_terms()]

    def facet_counts(self, facet_field):
        return self._results.groups(facet_field)

    @property
    def searcher(self):
        """@rtype: whoosh.searching.Searcher"""
        searcher = self._searcher
        if searcher is None:
            searcher_factory = self.searcher_factory
            if searcher_factory is not None:
                searcher = self._searcher = searcher_factory(self.index_name)
            else:
                raise Exception("Either searcher instance must be passed to query or searcher_factory set")
        return searcher

    def close(self):
        searcher = self._searcher
        if searcher is not None and not searcher.is_closed:
            searcher.close()

    def is_term_in_index(self, field_name, term_value):
        reader = self.searcher.reader()
        return (field_name, term_value) in reader

