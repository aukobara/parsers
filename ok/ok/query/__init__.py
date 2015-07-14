# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals, absolute_import
from ok.query.tokens import QueryItemBase

"""
This is a package for query processing modules like tokenizer, parsing context, etc
"""


def parse_query(q_str, predecessor_query=None, lowercase=True):
    """@rtype: ok.query.tokens.Query"""
    from ok.query.tokens import DefaultQuery, Query, EmptyQuery
    if not q_str:
        return EmptyQuery
    elif isinstance(q_str, Query):
        return q_str
    elif isinstance(q_str, list) and q_str and isinstance(q_str[0], QueryItemBase) and q_str[0].query is not None:
        query_type = q_str[0].query.__class__
        return query_type(q_str, predecessor_query=predecessor_query, lowercase=lowercase)
    else:
        return DefaultQuery(q_str, predecessor_query=predecessor_query, lowercase=lowercase)
