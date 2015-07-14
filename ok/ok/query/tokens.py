# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

from collections import defaultdict
import logging
import re

from ok.utils import ImmutableListMixin

RE_QUERY_SEPARATOR = '\s|"|,|\.|«|»|“|”|\(|\)|\?|!|\+|:'

log = logging.getLogger(__name__)


def cleanup_token_str(s):
    """
    Cleanup one-line string from non-label symbols - colon, quotes, periods etc
    Replace multi-spaces to single space. Strip
    @param unicode s: one-line string
    @rtype: unicode
    """
    return re.sub('(?:\s|"|,|\.|«|»|“|”|\(|\)|\?|\+|:)+', ' ', s).strip()


class QueryItemBase(unicode):

    # Mandatory attributes for token implementation classes (if they want to be parsed)
    regex = None
    group_name = None

    # Optional attributes
    pre_condition = None
    post_condition = None

    def __new__(cls, position, item_str, *_, **__):
        return unicode.__new__(cls, item_str)

    def __init__(self, position, item_str, char_pos, query=None):
        super(QueryItemBase, self).__init__(item_str)
        self.position = position
        self.query = query

        if isinstance(char_pos, slice):
            assert query is not None, "Must have access to original query string if slice specified as char position"
            char_start_at, char_end_to, _ = char_pos.indices(len(query.original_query))
            self.char_start = char_start_at
            self.char_end = char_end_to - 1
        else:
            # Not a slice - treat as int
            self.char_start = char_pos
            self.char_end = char_pos + len(item_str) - 1

    def __repr__(self):
        return '%d:%s:%s' % (self.position, super(QueryItemBase, self).__repr__(), type(self).__name__)

    def __unicode__(self):
        return self[:]

    def pre_item(self):
        assert self.query
        return self.query[self.position-1] if self.position >= 1 else None

    def post_item(self):
        assert self.query
        try:
            return self.query[self.position+1]
        except IndexError:
            return None

    @property
    def original(self):
        assert self.query
        return self.query.original_query[self.char_start:self.char_end + 1]


class QueryToken(QueryItemBase):
    """
    Base class for non-separator meaningful tokens
    """
    @property
    def pre_separator(self):
        item = self.pre_item()
        return item if isinstance(item, QuerySeparator) else None

    @property
    def post_separator(self):
        item = self.post_item()
        return item if isinstance(item, QuerySeparator) else None


class QueryWord(QueryToken):
    """
    Special class for words remaining after all other token classes.
    In general, it is all regular tokens without special parsing rules.
    """
    pass


class QuerySeparator(QueryItemBase):

    regex = '[%s]+' % RE_QUERY_SEPARATOR
    group_name = 'separator'


class Query(ImmutableListMixin, list):
    """
    Abstract Query class. In derived classes token_reg has to be assigned
    to list of Token classes inherited from QueryItemBase.
    """
    token_reg = None
    """@type: list"""

    def __init__(self, q_str, predecessor_query=None, lowercase=True):
        if isinstance(q_str, list):
            # Initialize from list of pre-parsed tokens of another query
            assert q_str and all(self.is_compatible_with_token(item) for item in q_str), \
                    "Query class '{query_type}' is not compatible with specified token list: {q}".format(
                        query_type=self.__class__, q=''.join(q_str))

            producer_query = q_str[0].query
            """@type: Query"""
            self.original_query = producer_query.original_query if producer_query else ''.join(q_str)

            self.predecessor_query = predecessor_query or producer_query
            """@type: Query"""

            super(Query, self).__init__(self.copy_items(q_str, parent_query=self, lowercase=lowercase))

        else:
            self.original_query = q_str

            self.predecessor_query = predecessor_query
            """@type: Query"""

            super(Query, self).__init__(self.split(q_str, parent_query=self, lowercase=lowercase))

    _regex = None
    _regex_ic = None

    @classmethod
    def is_compatible_with_token(cls, token):
        token_type = token if isinstance(token, type) else token.__class__
        return token_type == QueryWord or token_type in cls.token_reg

    @staticmethod
    def validate_token_class(token_cls):
        if issubclass(token_cls, QueryItemBase) and token_cls.group_name and token_cls.regex:
            regex = '(?P<%s>%s)' % (token_cls.group_name, token_cls.regex)
            try:
                re.compile(regex, re.U)
                if token_cls.pre_condition:
                    regex = token_cls.pre_condition
                    re.compile('(?<=%s)' % regex, re.U)
                if token_cls.post_condition:
                    regex = token_cls.post_condition
                    re.compile(regex, re.U)
                return True
            except Exception as e:
                log.error("Failed parsing regexp for token: %s. Error: %r. Regexp:\r\n%s", token_cls.__name__, e, regex)
                raise
        return False

    @classmethod
    def regex(cls, ignore_case=False):
        regex = cls._regex_ic if ignore_case else cls._regex
        if regex is None:
            regex = ''
            flags = re.UNICODE | re.IGNORECASE if ignore_case else re.UNICODE
            for i, token_cls in enumerate(cls.token_reg):
                assert cls.validate_token_class(token_cls), \
                    "Invalid token type class '{token_type!r}' is defined in query type '{query_type!r}'".format(token_type=token_cls, query_type=cls)
                if i > 0:
                    regex += '|'

                if token_cls.pre_condition:
                    regex += '(?:^|(?<=%s))' % token_cls.pre_condition

                regex += '(?P<%s>%s)' % (token_cls.group_name, token_cls.regex)

                if token_cls.post_condition:
                    regex += '(?=%s|$)' % token_cls.post_condition

            try:
                regex = re.compile(regex, flags)
            except Exception as e:
                log.error("Failed parsing regexp for query: %s. Error: %r. Regex:\r\n%s", cls.__name__, e, regex)
                raise

            if ignore_case:
                cls._regex_ic = regex
            else:
                cls._regex = regex
        return regex

    _group_to_type = None

    @classmethod
    def _token_group_name_to_type(cls):
        group_to_type = cls._group_to_type
        if group_to_type is None:
            group_to_type = cls._group_to_type = {token_type.group_name: token_type for token_type in cls.token_reg}
        return group_to_type

    @classmethod
    def copy_items(cls, items, parent_query=None, lowercase=True):
        # Recreate all query items from another query with specified attributes
        new_items = []
        for pos, token in enumerate(items):
            token_type = token.__class__
            assert cls.is_compatible_with_token(token_type)
            token_str = token.lower() if lowercase else token[:]
            new_items.append(token_type(pos, token_str, slice(token.char_start, token.char_end + 1), parent_query))
        return new_items

    @classmethod
    def split(cls, q_str, parent_query=None, lowercase=True):
        """
        Split q_str to sequence of query items, where each one is either QueryToken or TokenSeparator.
        Each item keeps its position in original string and reference to query object (if specified).
        Usually, Token and Separators items go one by another. However, it may be changed in implementations because logic of
        word boundary can be differ (e.g. lowerToUpper string can be treated as 'lower' 'to' 'upper' tokens without (or with empty)
        separator between them)
        @param unicode q_str: query string to parse
        @param Query|None parent_query: query consists of returned items. If specified position attribute of each item
                references to character in that query
        @param bool lowercase: if False, keep characters in items as is, call .lower() otherwise.
                Please note, characters in original query keeps as is and can be accessed by position if required.
        """
        assert cls.token_reg, "Query implementation class must define Token Types list in 'token_reg' attribute"
        result = []
        if q_str:
            if lowercase:
                q_str = q_str.lower()
                re_pattern = cls.regex(ignore_case=True)
            else:
                re_pattern = cls.regex(ignore_case=False)

            group_name_to_type_dict = cls._token_group_name_to_type()

            position = 0
            prev_char_at = 0

            start_iter_at = 0
            while start_iter_at < len(q_str):
                token_it = re.finditer(re_pattern, q_str[start_iter_at:])
                for token_match in token_it:
                    matched_groups = token_match.groupdict()
                    matched_items = filter(lambda _t: _t[1] is not None, matched_groups.items())
                    assert len(matched_items) == 1, 'Query patterns overlapping check is failed'
                    matched_group_name, item = matched_items[0]
                    token_cls = group_name_to_type_dict[matched_group_name]

                    match_char_at = token_match.start() + start_iter_at

                    """
                    if token_cls.pre_condition and match_char_at > 0:
                        pre_match = re.match('^.*%s$' % token_cls.pre_condition, q_str[:match_char_at], re_pattern.flags)
                        if pre_match is None:
                            # Pre-condition is not matched. Treat this as false-positive match and restart finditer from next char.
                            # Current char will join to previous word
                            start_iter_at = match_char_at + 1
                            break
                    """

                    if prev_char_at < match_char_at:
                        prev_word = q_str[prev_char_at:match_char_at]
                        result.append(QueryWord(position, prev_word, prev_char_at, query=parent_query))
                        position += 1

                    token = token_cls(position, item, match_char_at, query=parent_query)
                    result.append(token)
                    position += 1
                    prev_char_at = token_match.end() + start_iter_at
                else:
                    # Match iterator finished normally. No more cycles.
                    break

            if prev_char_at < len(q_str):
                    result.append(QueryWord(position, q_str[prev_char_at:], prev_char_at, query=parent_query))

            assert result, 'Separator pattern is not valid - empty result for query: %s' % q_str
            assert len(q_str) == sum(map(len, result))  # Check all characters are covered

        return result

    _to_str_cache = None

    def to_str(self, sep=''):
        if self._to_str_cache is not None:
            return self._to_str_cache
        rv = self._to_str_cache = sep.join(self)
        return rv

    def __unicode__(self):
        return self.to_str(' + ')

    _items_type_cache = None

    def items_of_type(self, type_cls):
        """@rtype: list[QueryItemBase]"""
        assert issubclass(type_cls, QueryItemBase) and (type_cls in self.token_reg or type_cls is QueryWord or type_cls is QueryToken), \
            "Query Item class %r is not registered in %r" % (type_cls, self.__class__)
        items_type_cache = self._items_type_cache
        if items_type_cache is None:
            items_type_cache = defaultdict(list)
            for item in self:
                item_type = item.__class__
                items_type_cache[item_type].append(item)
                if issubclass(item_type, QueryToken):
                    items_type_cache[QueryToken].append(item)
            self._items_type_cache = items_type_cache
        return items_type_cache.get(type_cls, [])[:]

    @property
    def tokens(self):
        """@rtype: list[QueryToken]"""
        return self.items_of_type(QueryToken)

    @property
    def words(self):
        """@rtype: list[QueryWord]"""
        return self.items_of_type(QueryWord)

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
        @param QueryItemBase token: what to replace
        @param unicode new_token_str: string of new token. Must not contain separator characters.
        @return: new query with predecessor_query as this query
        """
        assert isinstance(token, QueryItemBase) and token.query is self

        query_type = self.__class__
        token_type = token.__class__
        new_query = query_type(self.original_query, predecessor_query=self)
        new_token = token_type(token.position, new_token_str, slice(token.char_start, token.char_end + 1), query=new_query)
        # Query is immutable - call super method
        list.__setitem__(new_query, token.position, new_token)

        return new_query


class DefaultQuery(Query):

    token_reg = [QuerySeparator]

EmptyQuery = DefaultQuery("")