# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

import re

from ok.utils import ImmutableListMixin

RE_QUERY_SEPARATOR = '\s|"|,|\.|«|»|“|”|\(|\)|\?|!|\+|:'
RE_QUERY_PATTERN = re.compile('([%s]+)?([^%s]+)([%s]+)?|([%s]+)' % (RE_QUERY_SEPARATOR, RE_QUERY_SEPARATOR, RE_QUERY_SEPARATOR, RE_QUERY_SEPARATOR), re.U)
RE_QUERY_PATTERN_SEPARATOR = re.compile('([%s]+)?' % RE_QUERY_SEPARATOR, re.U)


def cleanup_token_str(s):
    """
    Cleanup one-line string from non-label symbols - colon, quotes, periods etc
    Replace multi-spaces to single space. Strip
    @param unicode s: one-line string
    @rtype: unicode
    """
    return re.sub('(?:\s|"|,|\.|«|»|“|”|\(|\)|\?|\+|:)+', ' ', s).strip()


class QueryItemBase(unicode):

    def __new__(cls, position, item_str, query=None):
        return unicode.__new__(cls, item_str)

    def __init__(self, position, item_str, query=None):
        super(QueryItemBase, self).__init__(item_str)
        self.position = position
        self.query = query

    def __repr__(self):
        return '%d:%s:%s' % (self.position, super(QueryItemBase, self).__repr__(), type(self))

    def pre_item(self):
        assert self.query
        return self.query[self.position-1] if self.position >= 1 else None

    def post_item(self):
        assert self.query
        try:
            return self.query[self.position+1]
        except IndexError:
            return None


class QueryToken(QueryItemBase):

    @property
    def pre_separator(self):
        item = self.pre_item()
        return item if isinstance(item, QuerySeparator) else None

    @property
    def post_separator(self):
        item = self.post_item()
        return item if isinstance(item, QuerySeparator) else None


class QuerySeparator(QueryItemBase):
    pass


class Query(ImmutableListMixin, list):

    def __init__(self, q_str, predecessor_query=None):
        self.original_query = q_str
        self.predecessor_query = predecessor_query
        """@type: Query"""
        super(Query, self).__init__(self.split(q_str, parent_query=self))

    @staticmethod
    def split(q_str, parent_query=None):
        result = []
        if q_str:
            token_it = re.finditer(RE_QUERY_PATTERN, q_str)
            position = 0
            for token_match in token_it:
                sep_only = token_match.group(4)
                if sep_only:
                    # Separator only variant
                    result.append(QuerySeparator(position, sep_only, query=parent_query))
                    position += 1
                else:
                    pre_sep = token_match.group(1)
                    token = token_match.group(2)
                    post_sep = token_match.group(3)
                    if pre_sep:
                        result.append(QuerySeparator(position, pre_sep, query=parent_query))
                        position += 1
                    result.append(QueryToken(position, token, query=parent_query))
                    position += 1
                    if post_sep:
                        result.append(QuerySeparator(position, post_sep, query=parent_query))
                        position += 1

            assert result, 'Separator pattern is not valid - empty result for query: %s' % q_str
            assert len(q_str) == sum(map(len, result))  # Check all characters are covered

        return result

    _to_str_cache = None

    def to_str(self):
        if self._to_str_cache is not None:
            return self._to_str_cache
        rv = self._to_str_cache = ''.join(self)
        return rv

    def __unicode__(self):
        return self.to_str()

    _tokens_cache = None

    @property
    def tokens(self):
        """@rtype: list[QueryToken]"""
        if self._tokens_cache is not None:
            return self._tokens_cache
        rv = self._tokens_cache = [token for token in self if isinstance(token, QueryToken)]
        return rv[:]

    def _hashed_items(self):
        return self.tokens

    # Index of query item that was changed comparing with predecessor query
    _last_changed_cache = None

    def last_changed_token(self, default_index=None):
        default = self[default_index] if default_index is not None else None

        if self._last_changed_cache is not None:
            return self[self._last_changed_cache] if self._last_changed_cache >= 0 else default

        self_tokens = self.tokens
        items_count = len(self_tokens)
        if items_count == 1:
            self._last_changed_cache = self_tokens[0].position
            return self[0]

        pq = self.predecessor_query
        if not pq:
            # Predecessor query is not specified
            self._last_changed_cache = -1
            return default

        pq_tokens = pq.tokens
        pq_count = pq_tokens and len(pq_tokens)
        if abs(items_count - pq_count) > 1:
            # Predecessor query is too different from this query
            self._last_changed_cache = -1
            return default

        # Queries are different but by one item only
        diff_idx = None
        shift = 0
        for i in range(min(items_count, pq_count)):
            self_current = i
            pq_current = i + shift
            if self_tokens[self_current] != pq_tokens[pq_current]:
                if diff_idx is not None:
                    # More than one item changed. Cannot determine result
                    diff_idx = None
                    break
                diff_idx = self_current
                if items_count != pq_count:
                    # Calculate shifts for queries with different len
                    self_next = self_current + 1
                    pq_next = pq_current + 1
                    if self_next < items_count and self_tokens[self_next] == pq_tokens[pq_current]:
                        # New item in self
                        shift = -1
                    elif pq_next < pq_count and self_tokens[self_current] == pq_tokens[pq_next]:
                        # Item deleted. Treat next after deleted as last edited
                        shift = 1
                    else:
                        diff_idx = None
                        break
        else:
            if diff_idx is None and items_count != pq_count:
                # Item appended or popped at the end
                diff_idx = items_count - 1

        self._last_changed_cache = self_tokens[diff_idx].position if diff_idx is not None else -1
        return self[self._last_changed_cache] if self._last_changed_cache >= 0 else default

    def replace_token(self, token, new_token_str):
        """
        Produces new Query object with one token replaced by another.
        @param QueryToken token: what to replace
        @param unicode new_token_str: string of new token. Must not contain separator characters.
        @return: new query with predecessor_query as this query
        """
        assert token.query is self

        new_query = Query(self.original_query, predecessor_query=self)
        new_token = QueryToken(token.position, new_token_str, query=new_query)
        # Query is immutable - call super method
        list.__setitem__(new_query, token.position, new_token)

        return new_query