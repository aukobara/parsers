# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals, absolute_import

"""
This is a package for query processing modules like tokenizer, parsing context, etc
"""

def parse_query(q_str, predecessor_query=None):
    from ok.query.tokens import Query
    return Query(q_str, predecessor_query=predecessor_query)

from ok.query.find import find_products, find_brands, RS
