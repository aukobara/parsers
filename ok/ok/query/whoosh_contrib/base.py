# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

import logging

from whoosh import sorting

log = logging.getLogger(__name__)

class BaseFindQuery(object):
    # Class attributes to override
    need_matched_terms = False
    index_name = None
    searcher_factory = None

    def __init__(self, q, searcher=None, return_fields=None, facet_fields=None, limit=10):
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

        self.limit = limit
        """@type: int"""

        # Accessor helper to current match document
        self._match = None
        """@type: whoosh.searching.Hit"""
        self._results = None
        """@type: whoosh.searching.Results"""

    @property
    def q_tokenized(self):
        q_tokenized = self._q_tokenized
        if q_tokenized is None:
            q_tokenized = self._q_tokenized = self._tokenize_query(self.q_original)
        return q_tokenized

    @staticmethod
    def _tokenize_query(q):
        """@rtype: ok.query.tokens.Query"""
        from ok.query import parse_query
        return parse_query(q)

    def query_variants(self):
        """
        @rtype: list[whoosh.query.qcore.Query]
        @return: list of whoosh queries to execute one by one until any result will be found.
            They must be sorted in order of priority (aka potentially more exact matches must go first)
        """
        raise NotImplementedError

    def __call__(self):
        searcher = self.searcher
        match_found = False
        return_one_field = return_all = None
        return_fields = self.return_fields

        limit = self.limit
        terms = self.need_matched_terms
        facets = self.facets
        search = self._search

        q_attempt = None
        for q_attempt in self.query_variants():

            if log.isEnabledFor(logging.DEBUG):
                log.debug("Searching for query: %s" % q_attempt)

            r = search(searcher, q_attempt, limit=limit, terms=terms, groupedby=facets)
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
            elif log.isEnabledFor(logging.DEBUG):
                log.debug("No matches found for query: %s. Trying next query" % q_attempt)

        # For last generator iteration keep last attempted query.
        # It can be useful for analysis of empty result
        self.matched_query = q_attempt

    def _search(self, searcher, whoosh_query, **kwargs):
        """
        This method encapsulate one whoosh query attempt logic. It can be overridden by implementations to add
        some logic like: post-filtering, query enhancement, more precise result size estimations, Results object wrapping,
        whoosh internals tuning (e.g. replacement matcher or/and collector).
        kwargs parameters are the same as for whoosh.searching.Searcher#search method. Main are described further:
        @param whoosh.searching.Searcher searcher: index searcher
        @param whoosh.query.qcore.Query whoosh_query: one of query produced by @query_variants()
        @param int|None limit: max number of results to return. If None returns all. If not specified whoosh defaults this to 10
        @param bool terms: If True collect matching terms for later use by caller logic. Some implementations can ignore this flag and implement
                matching terms by their own
        @param whoosh.sorting.Facets|None groupedby: if facets collection is required.
        @return: whoosh Results like API object. Actually this can by any proxy object with required __iter__ implementation as well as __len__ methods.
                    Also it will require groups() method implementation if facets we specified for this query
        @rtype: whoosh.searching.Results
        """
        return searcher.search(whoosh_query, **kwargs)

    # Current match object accessor helpers
    @property
    def current_match(self):
        return self._match

    @property
    def matched_tokens(self):
        """
        @rtype: list[ok.query.tokens.QueryToken]
        @return: list of tuples (field_name, term_value)
        """
        assert self.need_matched_terms, "Query class %r must set 'need_matched_terms' to access matched terms data" % self.__class__
        m_terms = frozenset(t[1].decode('utf-8') for t in self.current_match.matched_terms())
        result = []
        for token in self.q_tokenized.tokens:
            if token in m_terms:
                result.append(token)
        return result

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

    def expand_term_prefix(self, field_name, term_prefix):
        reader = self.searcher.reader()
        """@type: whoosh.reading.IndexReader"""
        for term in reader.expand_prefix(field_name, term_prefix):
            yield term.decode('utf-8')
