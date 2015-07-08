# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals, absolute_import

"""
This is a package for query processing modules like tokenizer, parsing context, etc
"""


def parse_query(q_str, predecessor_query=None, lowercase=True):
    from ok.query.tokens import DefaultQuery, Query
    return q_str if isinstance(q_str, Query) else DefaultQuery(q_str, predecessor_query=predecessor_query, lowercase=lowercase)
