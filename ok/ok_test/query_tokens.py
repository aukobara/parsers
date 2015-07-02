# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals

from ok.query import parse_query
from ok.query.tokens import QueryToken, QuerySeparator


def test_query_parse():
    q = parse_query(' тст."тст"тест1 тест2 !')
    assert len(q) == 9
    assert all(isinstance(t, QuerySeparator) for t in q[::2])
    assert all(isinstance(t, QueryToken) for t in q[1::2])
    assert [t.position for t in q] == range(9)


def test_query_parse_empty():
    assert parse_query(None) == []
    assert parse_query('') == []

    q = parse_query('...')
    assert len(q) == 1
    assert isinstance(q[0], QuerySeparator)
    assert q[0] == '...'


def test_query_tokens():
    q = parse_query(' тст."тст"тест1 тест2 !')
    tokens = q.tokens
    assert tokens == ['тст', 'тст', 'тест1', 'тест2']
    assert all(isinstance(t, QueryToken) for t in tokens)


def test_pre_post_separator():
    q = parse_query('тст.тст...')
    t1, t2 = q.tokens
    assert t1.pre_separator is None
    assert t1.post_separator == '.'
    assert t2.pre_separator == '.'
    assert t2.post_separator == '...'


def test_hash():
    q1 = parse_query('тст')
    d = {q1: 1}  # Assert dict accepts query as a key
    assert d[q1] == 1

    q2 = parse_query('...тст...')
    assert q1.__hash__() == q2.__hash__()


def test_last_changed_one_item():
    q1 = parse_query('тест')
    q2 = parse_query('тест', predecessor_query=q1)
    assert q2.last_changed_token() == 'тест'

    q2 = parse_query('тест1', predecessor_query=q1)
    assert q2.last_changed_token() == 'тест1'


def test_last_changed_multi_item():
    q1 = parse_query('тест тест2 тест3')

    q2 = parse_query('тест тест2 тест3', predecessor_query=q1)
    assert q2.last_changed_token() is None
    assert q2.last_changed_token(default_index=-1) == 'тест3'

    q2 = parse_query('тест тест22 тест3', predecessor_query=q1)
    assert q2.last_changed_token() == 'тест22'

    q2 = parse_query('тест41 тест тест2 тест3', predecessor_query=q1)
    assert q2.last_changed_token() == 'тест41'

    q2 = parse_query('тест тест2 тест42 тест3', predecessor_query=q1)
    assert q2.last_changed_token() == 'тест42'

    q2 = parse_query('тест тест2 тест3 тест42', predecessor_query=q1)
    assert q2.last_changed_token() == 'тест42'

    q2 = parse_query('тест тест2', predecessor_query=q1)
    assert q2.last_changed_token() == 'тест2'

    q2 = parse_query('тест тест22 тест3 тест5', predecessor_query=q1)
    assert q2.last_changed_token() is None


def test_replace():
    q1 = parse_query('тест1 "тест2" тест3')
    q2 = q1.replace_token(q1.tokens[1], 'тест22')
    assert q2.to_str() == 'тест1 "тест22" тест3'
    assert q2.predecessor_query is q1
    # Check original query has not been changed
    assert q1.to_str() == 'тест1 "тест2" тест3'
