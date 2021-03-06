# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals

from ok.query import parse_query
from ok.query.tokens import QueryToken, QuerySeparator, Query, DefaultQuery


def test_query_parse():
    q_str = ' тст."тст"тест1 тест2 !'
    q = parse_query(q_str)
    _assert_regular_query(q, 9)


def _assert_regular_query(q, num_items):
    assert len(q) == num_items
    assert all(isinstance(t, QuerySeparator) for t in q[::2])
    assert all(isinstance(t, QueryToken) for t in q[1::2])
    assert [t.position for t in q] == range(num_items)


def test_query_char_positions():
    q_str = ' тст."тст"тест1 тест2 !'
    q = parse_query(q_str)
    assert [(t.char_start, t.char_end) for t in q] == [(0, 0), (1, 3), (4, 5), (6, 8), (9, 9), (10, 14), (15, 15), (16, 20), (21, 22)]
    assert all(q_str[t.char_start:t.char_end+1] == t.original for t in q)


def test_query_parse_case_sensitive():
    q_str = ' тСт."Тст"тЕСТ1 ТЕСТ2 !'
    q = parse_query(q_str, lowercase=False)
    _assert_regular_query(q, 9)
    assert all(q_str[t.char_start:t.char_end+1] == t.original for t in q)
    # Check case was not changed in tokens
    assert all(q_str[t.char_start:t.char_end+1] == t for t in q)

    q = parse_query(q_str, lowercase=True)
    assert q.original_query == q_str
    _assert_regular_query(q, 9)
    # Check original returns not changed copy of items
    assert all(q_str[t.char_start:t.char_end+1] == t.original for t in q)
    # Check case was changed in tokens now
    assert all(q_str[t.char_start:t.char_end+1] != t and q_str[t.char_start:t.char_end+1].lower() == t for t in q.tokens)


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
    assert q2.tokens[1].original == 'тест2'

def test_recursive_query():
    q = parse_query('тест1 "тест2" тест3')
    _test_recursive_query_base(q)

def _test_recursive_query_base(q1):
    q2 = parse_query(q1)
    assert q1 is q2

    q3 = parse_query(q1.tokens)
    assert q3 is not q1
    assert ''.join(q3) == ''.join(q1.tokens)
    assert [item.position for item in q3] == range(0, len(q3))
    assert q3.original_query == q1.original_query
    assert q3.predecessor_query is q1
    assert all(token.query is q3 for token in q3)

class _TestQuery(Query):
    class TestToken(QueryToken):
        regex = 'тест123'
        group_name = 'test_group'

    class TestTokenPre(QueryToken):
        regex = '\d+\s+шт'
        group_name = 'test_group_pre'
        pre_condition = '\D'

    class TestTokenPost(QueryToken):
        regex = 'тест44'
        group_name = 'test_group44'
        post_condition = QuerySeparator.regex

    token_reg = [TestToken, TestTokenPost, TestTokenPre] + DefaultQuery.token_reg

def test_custom_query():
    q = _TestQuery('тест123 тест1234')
    assert q.tokens == ['тест123', 'тест123', '4']
    assert q.items_of_type(_TestQuery.TestToken) == ['тест123', 'тест123']
    assert q.words == ['4']

def test_custom_query_conditions():
    q = _TestQuery('тест1234шт "тест445" тест44.т56 шт')
    assert q.tokens == ['тест123', '4шт', 'тест445', 'тест44', 'т', '56 шт']
    assert q.items_of_type(_TestQuery.TestToken) == ['тест123']
    assert q.items_of_type(_TestQuery.TestTokenPost) == ['тест44']
    assert q.items_of_type(_TestQuery.TestTokenPre) == ['56 шт']
    assert q.words == ['4шт', 'тест445', 'т']

def test_custom_query_recursion():
    q = _TestQuery('тест1234шт "тест445" тест44.т56 шт')
    _test_recursive_query_base(q)