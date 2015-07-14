# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
from collections import defaultdict
from functools import wraps
import pytest

from ok.dicts import main_options
from ok.utils import to_str
from ok.dicts.product import Product
from ok.dicts.product_type import ProductType
from ok.dicts.product_type_dict import reload_product_type_dict, ProductTypeDict
from ok.dicts.russian import get_word_normal_form
from ok.dicts.term import load_term_dict, TypeTerm, ContextRequiredTypeTermException, dump_term_dict_from_product_types, \
    CompoundTypeTerm, ContextDependentTypeTerm, ctx_def, DEFAULT_CONTEXT, WithPropositionTypeTerm, TermContext, \
    context_aware


@pytest.fixture(autouse=True)
def clear_terms_dict():
    TypeTerm.term_dict.clear()

@pytest.fixture
def pdt():
    config = main_options([], baseline_dir='resources/test', product_types_in_json='product_types_test_mar.json')
    _pdt = reload_product_type_dict(config)
    return _pdt

@pytest.fixture
def term_dict_full():
    term_dict = load_term_dict()
    return term_dict

@pytest.fixture
def pdt_full(term_dict_full):
    # TODO: rewrite to parametrized fixture
    _pdt = reload_product_type_dict(config=None)
    return _pdt


def test_context_terms_find_compound(pdt):
    rel = pdt.find_product_type_relations(u'продукт йогуртный перс/мар/ананас/дыня')

    _assert_prod_mar_types(rel)

    pt_mar = ProductType(u'продукт', u'йогуртный', u'мар')
    pt_mar_full = ProductType(u'продукт', u'йогуртный', u'маракуйя')
    eq_relation = pt_mar.equals_to(pt_mar_full, dont_change=True)
    assert eq_relation in rel[pt_mar]

    # Only in test data
    pt_mar_bad = ProductType(u'продукт', u'мар')
    subset_of_relation = pt_mar.subset_of(pt_mar_bad, dont_change=True)
    assert subset_of_relation in rel[pt_mar]


def test_context_terms_parse_compound(pdt):
    types = pdt.collect_sqn_type_tuples(u'продукт йогуртный перс/мар/ананас/дыня')
    _assert_prod_mar_types(types)

def test_context_terms_parse_expand_abbr(pdt):
    types = pdt.collect_sqn_type_tuples('коктейль молочный стерилиз')
    _assert_all_types_are_finalized(types)

    pt_full = ProductType('коктейль', 'молочный', 'стерилизованный')

    assert pt_full in types

def test_context_terms_parse_match_with_prop():
    pdt = ProductTypeDict()
    pdt.min_meaningful_type_capacity = 2
    """@param ProductTypeDict pdt: pdt"""
    sqn1 = 'приправа лимонная к рыбе'
    p1 = Product({'sqn': sqn1})

    sqn2 = 'приправа лимонная для рыбы'
    p2 = Product({'sqn': sqn2})

    pdt.build_from_products([p1, p2], strict_products=False)
    types = pdt.get_type_tuples(meaningful_only=True)
    _assert_all_types_are_finalized(types)

    pt_full = ProductType('приправа', 'лимонная', 'рыба')
    assert pt_full in types
    assert types[pt_full] == [sqn1, sqn2]
    assert pt_full.relations()

    p1_types = pdt.find_product_types(sqn1)
    assert pt_full in p1_types
    p2_types = pdt.find_product_types(sqn2)
    assert pt_full in p2_types

def test_context_terms_main_form_with_compatible_compound(pdt):
    term_comp = TypeTerm.make('продукт-йогуртный')
    term_context_req = TypeTerm.make('мар')
    context = [term_comp, term_context_req]

    term_main = term_context_req.get_main_form(context=context)
    assert term_main == 'маракуйя'

def test_context_terms_compound_main_form_with_compatible_compound(pdt):
    term_comp = TypeTerm.make('продукт-йогуртный')
    term_context_req = TypeTerm.make('перс/мар/ананас/дыня')
    context = [term_comp, term_context_req]

    assert isinstance(term_comp, CompoundTypeTerm)
    term_main = term_context_req.get_main_form(context=context)
    assert term_main == 'персик маракуйя ананас дыня'
    assert isinstance(term_context_req, CompoundTypeTerm)
    sub_term_context_req = term_context_req.simple_sub_terms[1]
    assert sub_term_context_req == 'мар'
    with pytest.raises(ContextRequiredTypeTermException):
        sub_term_context_req.get_main_form()
    sub_term_main = sub_term_context_req.get_main_form(context=context)
    assert sub_term_main == 'маракуйя'


def test_context_expand_compound():
    context_list = ['продукт-йогуртный', 'перс/мар/ананас/дыня']
    context = TermContext.ensure_context(context_list)

    assert all(isinstance(t, TypeTerm) for t in context)
    assert list(context) == ['продукт-йогуртный', 'перс/мар/ананас/дыня', 'продукт', 'йогуртный', 'перс', 'мар',
                             'ананас', 'дыня']


def test_context_non_term():
    context_list = ['терм', '_']
    context = TermContext.ensure_context(context_list)

    assert list(context) == [TypeTerm.make('терм'), '_']
    assert not isinstance(context[1], TypeTerm)
    assert '_' in context.not_a_terms


def test_context_terms_parse_with_compatible_compound(pdt):
    types = pdt.collect_sqn_type_tuples(u'продукт-йогуртный перс/мар/ананас/дыня')
    _assert_prod_mar_types(types)


def test_context_terms_parse_two_at_once(pdt):
    context_terms_def = ContextDependentTypeTerm.ctx_dependent_terms
    mar_def = context_terms_def['мар'][0]
    context_terms_def['тестт'] = [ctx_def(mar_def.ctx_terms, 'тесттерм')]
    types = pdt.collect_sqn_type_tuples(u'продукт-йогуртный перс/мар/ананас/дыня тестт')
    _assert_prod_mar_types(types)

    p = ProductType('продукт', 'йогуртный', 'маракуйя', 'тесттерм')
    assert p in types

    # tear down
    del context_terms_def['тестт']


def test_context_terms_default_as_self(pdt):
    context_terms_def = ContextDependentTypeTerm.ctx_dependent_terms
    context_terms_def['тестт'] = [ctx_def([DEFAULT_CONTEXT], 'тестт')]
    prev_id = TypeTerm.term_dict.get_max_id()

    t = TypeTerm.make('тестт')
    assert isinstance(t, ContextDependentTypeTerm)
    assert t.get_main_form(context=[t]) == 'тестт'
    assert t.all_context_main_forms() == [t]
    assert t.all_context_word_forms() == [t]
    assert prev_id + 1 == TypeTerm.term_dict.get_max_id(), \
        "Some weird terms created over term itself. 'Default' as term?"

    # tear down
    del context_terms_def['тестт']

def test_context_terms_default_as_self_prefix(pdt):
    context_terms_def = ContextDependentTypeTerm.ctx_dependent_terms
    context = ['контекст']
    context_terms_def['тес'] = [ctx_def([DEFAULT_CONTEXT], 'тестт'), ctx_def(context, 'тесттовый')]

    t_prefix = TypeTerm.make('тест')
    assert isinstance(t_prefix, ContextDependentTypeTerm)
    assert t_prefix.is_prefix()
    assert t_prefix.get_main_form(context=context) == 'тесттовый'
    assert t_prefix.word_forms(context=context) == ['тесттовый', t_prefix]
    assert set(t_prefix.all_context_main_forms()) == {'тестт', 'тесттовый'}
    assert set(t_prefix.all_context_word_forms()) == {'тестт', 'тесттовый', t_prefix}

    # tear down
    del context_terms_def['тес']

def test_context_terms_prefix_has_no_short_contexts(pdt):
    # Prefix ctx dependent term must not use contexts where it is not a prefix of full term
    context_terms_def = ContextDependentTypeTerm.ctx_dependent_terms
    context = ['контекст']
    context_terms_def['тст'] = [ctx_def(context, 'тст'), ctx_def([DEFAULT_CONTEXT], 'тстполный')]

    t_prefix = TypeTerm.make('тстп')
    assert isinstance(t_prefix, ContextDependentTypeTerm)
    assert t_prefix.is_prefix()
    assert t_prefix.get_main_form(context=context) == 'тстполный'
    assert t_prefix.word_forms(context=context) == ['тстполный', t_prefix]
    assert set(t_prefix.all_context_main_forms()) == {'тстполный'}
    assert set(t_prefix.all_context_word_forms()) == {'тстполный', t_prefix}

    # tear down
    del context_terms_def['тст']

def test_context_terms_def_consistent():
    context_terms_def = ContextDependentTypeTerm.ctx_dependent_terms
    context = ['контекст']
    context_terms_def['тестт'] = [ctx_def(context, 'тестт')]

    t = TypeTerm.make('тестт')
    assert isinstance(t, ContextDependentTypeTerm)
    assert t.get_main_form(context=context) == 'тестт'
    assert t.all_context_main_forms() == [t]
    assert t.all_context_word_forms() == [t]

    # Change definitions. Expect terms and prefixes refresh their defs as well
    context_terms_def['тестт'] = [ctx_def(context, 'тестт2')]
    assert t is TypeTerm.make('тестт')
    assert t.get_main_form(context=context) == 'тестт2'
    assert t.all_context_main_forms() == ['тестт2']
    assert t.all_context_word_forms() == ['тестт2', t]

    # tear down
    del context_terms_def['тестт']

def test_context_terms_def_consistent_prefix():
    context_terms_def = ContextDependentTypeTerm.ctx_dependent_terms
    context = ['контекст']
    context_terms_def['тестт'] = [ctx_def(context, 'тесттпрефикс')]

    t = TypeTerm.make('тесттпреф')
    assert isinstance(t, ContextDependentTypeTerm)
    assert t.get_main_form(context=context) == 'тесттпрефикс'
    assert t.all_context_main_forms() == ['тесттпрефикс']
    assert t.all_context_word_forms() == ['тесттпрефикс', t]

    # Change definitions. Expect terms and prefixes refresh their defs as well
    context_terms_def['тестт'] = [ctx_def(context, 'тесттпрефикс2')]
    assert t is TypeTerm.make('тесттпреф')
    assert t.get_main_form(context=context) == 'тесттпрефикс2'
    assert t.all_context_main_forms() == ['тесттпрефикс2']
    assert t.all_context_word_forms() == ['тесттпрефикс2', t]

    # tear down
    del context_terms_def['тестт']

def test_context_terms_default_all(pdt):
    context_terms_def = ContextDependentTypeTerm.ctx_dependent_terms

    for term_str in context_terms_def:
        print("Current term: %s" % term_str)
        t = TypeTerm.make(term_str)
        context = [TypeTerm.make(ct) for ct in context_terms_def[term_str][0].ctx_terms]
        assert isinstance(t, ContextDependentTypeTerm)
        main_form = t.get_main_form(context=context)
        assert main_form == get_word_normal_form(context_terms_def[term_str][0].main_form)

def test_context_prefixed_terms():
    prefix_ctx_terms = [TypeTerm.make('шоко'), TypeTerm.make('шокол')]
    t_base = TypeTerm.make('шок')
    t_norm = TypeTerm.make('шоколад')
    t_ctx = TypeTerm.make('батончик')

    for t in prefix_ctx_terms:
        assert isinstance(t, ContextDependentTypeTerm)
        assert t.is_prefix()
        if len(t) <= 4:
            with pytest.raises(ContextRequiredTypeTermException):
                t.get_main_form(context=None)
        else:
            # For long prefix terms simplified context must be built
            t.get_main_form(context=None)
        main_form = t.get_main_form(context=[t, t_ctx])
        assert main_form == t_norm
        wf_base = set(t_base.word_forms([t_base, t_ctx])) - {t_base}
        wf_t = set(t.word_forms([t, t_ctx])) - {t}
        assert wf_base and wf_t and wf_base == wf_t

    assert not isinstance(t_norm, ContextDependentTypeTerm)

def test_context_prefixed_terms_product_load(pdt):
    p = Product(sqn='кисломол прод', tags={'Молочные продукты'})
    types = pdt.collect_type_tuples([p])
    _assert_all_types_are_finalized(types)
    assert ProductType('кисломолочный', 'продукт') in types

def test_context_terms_compound_context_product_load(pdt):
    p = Product(sqn='семечки-подсолн жареные станичные', tags={'овощи, фрукты, грибы, ягоды', 'орехи, сухофрукты'})
    types = pdt.collect_type_tuples([p])
    _assert_all_types_are_finalized(types)
    assert ProductType('семя', 'подсолнечник') in types

def test_context_terms_compound_context_product_load_very_slow(pdt):
    p = Product(sqn='конфеты-классик в мол/гор шок', tags={''})
    types = pdt.collect_type_tuples([p])
    _assert_all_types_are_finalized(types)
    assert ProductType('конфета', 'молоко', 'горький', 'шоколад') in types

def _assert_all_types_are_finalized(types):
    """@param set[ProductType]|list[ProductType]|dict of (ProductType, Any) types: container of ProductTypes"""
    for t in types:
        try:
            list(t.get_main_form_term_ids())
        except ContextRequiredTypeTermException:
            print("Test failed: All types after parse must be in terminal context")
            raise

def _assert_prod_mar_types(types):
    """@param set[ProductType]|list[ProductType]|dict of (ProductType, Any) types: container of ProductTypes"""
    _assert_all_types_are_finalized(types)

    pt_mar = ProductType(u'продукт', u'йогуртный', u'мар')
    pt_mar_bad = ProductType(u'продукт', u'мар')
    pt_mar_not_context = ProductType(u'продукт', u'маракуйя')
    pt_mar_full = ProductType(u'продукт', u'йогуртный', u'маракуйя')

    assert pt_mar_bad not in types
    assert pt_mar in types
    assert pt_mar_full in types
    assert pt_mar_not_context in types


def test_context_terms_parse_compound_proposition(pdt):
    types = pdt.collect_sqn_type_tuples(u'продукт йогуртный с мар')

    _assert_prod_mar_types(types)

    pt_mar_bad = ProductType(u'продукт', u'с мар')
    pt_mar_prop = ProductType(u'продукт', u'йогуртный', u'с мар')

    assert pt_mar_bad not in types
    assert pt_mar_prop in types


def test_context_terms_parse_compound_proposition_with_dict(pdt):
    terms = TypeTerm.parse_term_string(u'конфеты в гор шок')
    main_key_set = {term.get_main_form(context=terms).term_id for term in terms}

    pt_full = ProductType(u'конфеты', u'в горьком', u'шоколаде')
    pt_not_context = ProductType(u'конфеты', u'горький')
    pt_not_context_prop = ProductType(u'конфеты', u'в шоколаде')
    pt_bad = ProductType(u'конфеты', u'в гор')

    assert set(pt_full.get_main_form_term_ids()) == main_key_set
    assert set(pt_not_context.get_main_form_term_ids()) < main_key_set
    assert set(pt_not_context_prop.get_main_form_term_ids()) < main_key_set
    with pytest.raises(ContextRequiredTypeTermException):
        pt_bad.get_main_form_term_ids()

    assert isinstance(terms[1], WithPropositionTypeTerm)
    assert 'в гор' in terms[1].word_forms(context=terms)
    assert 'горький' in terms[1].word_forms(context=terms)
    assert 'в горький' in terms[1].word_forms(context=terms)


def test_context_terms_parse_ambiguous_with_dict(pdt):
    types = pdt.collect_sqn_type_tuples('продукт мол-раст сгущ с сахаром сгущенка с кофе')

    pt_full = ProductType('продукт', 'молоко', 'сгущенка')
    pt_not_context = ProductType('продукт', 'растворимый', 'с кофе')
    pt_comp_context = ProductType('продукт', 'молоко', 'растворимый', 'с кофе')

    assert pt_full in types
    assert pt_not_context in types
    assert pt_comp_context in types
    pt_full_wo_ambiguity_terms = ProductType('продукт', 'с сахаром', 'сгущенка')
    assert pt_full_wo_ambiguity_terms in types

    # Change first (priority) word
    types = pdt.collect_sqn_type_tuples(u'сгущ продукт мол-раст с сахаром сгущенка с кофе')

    assert pt_full not in types
    assert pt_not_context not in types
    assert pt_comp_context not in types
    pt_full_wo_ambiguity_terms = ProductType('сгущ', 'продукт', 'с сахаром')
    assert pt_full_wo_ambiguity_terms in types


def test_context_compound_self_sufficient_context():
    t_context_req = TypeTerm.make('туш')
    assert t_context_req.is_context_required()

    t = TypeTerm.make('говядина.туш')
    assert isinstance(t, CompoundTypeTerm)
    assert not t.is_context_required()
    assert t.get_main_form(context=None) == 'говядина тушёный'

def test_compound_spaced_recursive_main_form():
    # Pepsi has known word_normal_form 'Pepsi-Cola'. That may produce recursion when calculate all spaced main form
    term_str = 'тест1-тест2'

    class TestTerm(TypeTerm):
        def get_main_form(self, context=None):
            return TypeTerm.make(term_str)

    term1 = TestTerm('тест1')
    term2 = TestTerm('тест2')
    assert term1.get_main_form() == term_str
    assert term2.get_main_form() == term_str

    term_pre = TypeTerm.make('тестпре')
    term_post = TypeTerm.make('тестпост')
    term = TypeTerm.make(' '.join([term_pre, term_str, term_post]))

    for i in range(2):
        main_form = term.get_main_form()
        assert isinstance(main_form, CompoundTypeTerm)
        assert main_form == 'тестпре тест1 тест2 тестпост'
        assert main_form.simple_sub_terms == [term_pre, term1, term2, term_post]
        term = main_form

def test_compound_spaced_recursive_main_form_with_tranform():
    # 'Славянский' has known word_normal_form 'Церковно-Славянский' and 'Церковно' transforms to 'Церковь'.
    # That may produce recursion when calculate all spaced main form. Also check that other words are not touched
    term_str = 'тест1-тест2'
    term1_trans = TypeTerm.make('тест1транс')

    class TestTerm(TypeTerm):
        def get_main_form(self, context=None):
            return TypeTerm.make(term_str)

    class TestTermTrans(TypeTerm):
        def get_main_form(self, context=None):
            return term1_trans

    term1 = TestTermTrans('тест1')
    term2 = TestTerm('тест2')
    assert term1.get_main_form() == term1_trans
    assert term2.get_main_form() == term_str

    term_pre = TypeTerm.make('тестпре')
    term_post = TypeTerm.make('тестпост')
    term = TypeTerm.make(' '.join([term_pre, term1, term_str, term_post]))

    for i in range(2):
        main_form = term.get_main_form()
        assert main_form == 'тестпре тест1транс тест1 тест2 тестпост'
        term = main_form

def test_context_terms_fail_on_context():
    t = TypeTerm.make('мол-шок')
    context = [t]

    with pytest.raises(ContextRequiredTypeTermException):
        t.word_forms(context=context, fail_on_context=True)

    wf = t.word_forms(context=context, fail_on_context=False)
    assert wf is None

    # Check that failed result is not cached
    with pytest.raises(ContextRequiredTypeTermException):
        t.word_forms(context=context, fail_on_context=True)


def test_context_terms_all_def_contexts():
    for t_str, t_defs in ContextDependentTypeTerm.ctx_dependent_terms.viewitems():
        t = TypeTerm.make(t_str)
        assert isinstance(t, ContextDependentTypeTerm)
        all_forms = t.all_context_word_forms()
        t_forms = {t} | {get_word_normal_form(t_def.main_form) for t_def in t_defs if t_def.main_form != t_str}
        assert set(all_forms) == t_forms


def test_context_aware():

    class test_term(TypeTerm):
        @context_aware
        def test_context(self, context=None):
            """@param TestContext|list[TypeTerm|unicode]|None context: context"""
            assert isinstance(context, TermContext)
            context_key = context.call_key(test_term.test_context.context_aware_index, self.term_id)
            context_key_inner = context.call_key(test_term.test_context_inner.context_aware_index, self.term_id)
            context_key_inner2 = context.call_key(test_term.test_context_inner2.context_aware_index, self.term_id)

            assert context.is_marked_as_self(context_key)
            self.test_context_inner(context=context)
            assert context.is_marked_as_self(context_key)
            assert not context.is_marked_as_self(context_key_inner)
            self.test_context_inner2(context=context)
            assert context.is_marked_as_self(context_key)
            assert not context.is_marked_as_self(context_key_inner2)

        @context_aware
        def test_context_inner(self, context=None):
            """@param TestContext|list[TypeTerm|unicode]|None context: context"""
            assert isinstance(context, TermContext)
            context_key = context.call_key(test_term.test_context.context_aware_index, self.term_id)
            context_key_inner = context.call_key(test_term.test_context_inner.context_aware_index, self.term_id)

            assert context.is_marked_as_self(context_key)
            assert context.is_marked_as_self(context_key_inner)

        @context_aware
        def test_context_inner2(self, context=None):
            """@param TestContext|list[TypeTerm|unicode]|None context: context"""
            assert isinstance(context, TermContext)
            context_key = context.call_key(test_term.test_context.context_aware_index, self.term_id)
            context_key_inner2 = context.call_key(test_term.test_context_inner2.context_aware_index, self.term_id)

            assert context.is_marked_as_self(context_key)
            assert context.is_marked_as_self(context_key_inner2)

    t1 = test_term('тесттерм')
    context_list = ['терм1', 'терм2']
    t1.test_context(context=context_list)


def test_context_aware_prof(num_times=1):

    class test_term(TypeTerm):
        @context_aware
        def test_context(self, context=None):
            """@param TestContext|list[TypeTerm|unicode]|None context: context"""
            self.test_context_inner(context=context)

        @context_aware
        def test_context_inner(self, context=None):
            """@param TestContext|list[TypeTerm|unicode]|None context: context"""
            with pytest.raises(ContextRequiredTypeTermException):
                self.test_context(context=context)

    t1 = test_term('тесттерм')
    _context = TermContext(['терм1', 'терм2'])
    for i in range(num_times):
        t1.test_context(context=_context)


def test_context_aware_recursion():

    class test_term(TypeTerm):
        @context_aware
        def test_context(self, context=None):
            """@param TestContext|list[TypeTerm|unicode]|None context: context"""
            assert isinstance(context, TermContext)
            context_key = context.call_key(test_term.test_context.context_aware_index, self.term_id)
            context_key_inner = context.call_key(test_term.test_context_inner.context_aware_index, self.term_id)
            context_key_inner2 = context.call_key(test_term.test_context_inner2.context_aware_index, self.term_id)

            assert context.is_marked_as_self(context_key)
            self.test_context_inner(context=context)
            assert context.is_marked_as_self(context_key)
            assert not context.is_marked_as_self(context_key_inner)
            assert not context.is_marked_as_self(context_key_inner2)

        @context_aware
        def test_context_inner(self, context=None):
            """@param TermContext|list[TypeTerm|unicode]|None context: context"""
            context_key = context.call_key(test_term.test_context.context_aware_index, self.term_id)
            context_key_inner = context.call_key(test_term.test_context_inner.context_aware_index, self.term_id)

            assert context.is_marked_as_self(context_key)
            assert context.is_marked_as_self(context_key_inner)
            self.test_context_inner2(context=context)

        @context_aware
        def test_context_inner2(self, context=None):
            """@param TermContext|list[TypeTerm|unicode]|None context: context"""
            context_key = context.call_key(test_term.test_context.context_aware_index, self.term_id)
            context_key_inner = context.call_key(test_term.test_context_inner.context_aware_index, self.term_id)
            context_key_inner2 = context.call_key(test_term.test_context_inner2.context_aware_index, self.term_id)

            assert context.is_marked_as_self(context_key)
            assert context.is_marked_as_self(context_key_inner)
            assert context.is_marked_as_self(context_key_inner2)
            with pytest.raises(ContextRequiredTypeTermException):
                self.test_context(context=context)
            with pytest.raises(ContextRequiredTypeTermException):
                self.test_context_inner(context=context)
            with pytest.raises(ContextRequiredTypeTermException):
                self.test_context_inner2(context=context)

    t1 = test_term('тесттерм')
    context_list = ['терм1', 'терм2']
    t1.test_context(context=context_list)


def test_context_cache_exceptions():
    get_main_form_orig = ContextDependentTypeTerm.get_main_form
    term_exc_counts = defaultdict(int)

    @wraps(ContextDependentTypeTerm.get_main_form)
    def count_exc(*args, **kwargs):
        try:
            return get_main_form_orig(*args, **kwargs)
        except ContextRequiredTypeTermException as cre:
            _context = args[1] if len(args) == 2 else kwargs.get('context')
            if _context and 'Cannot find definition for context dependent term' in cre.message:
                term_exc_counts[args[0]] += 1
            raise
    ContextDependentTypeTerm.get_main_form = count_exc

    t = TypeTerm.parse_term_string('гор шок мол продукт')
    context = TermContext.ensure_context(t)
    assert t[2].get_main_form(context=context) == 'молоко'
    assert term_exc_counts.viewkeys() == {'гор', 'шок'}
    assert term_exc_counts['гор'] == 1  # If exception cache does not work here will be 2
    assert term_exc_counts['шок'] == 2
    # Tear down
    ContextDependentTypeTerm.get_main_form = get_main_form_orig

def test_context_recursive_def(pdt):
    ctx_dependent_terms = ContextDependentTypeTerm.ctx_dependent_terms
    assert 'том' in ctx_dependent_terms
    assert any(ctx_def.main_form == 'томатный' for ctx_def in ctx_dependent_terms['том'])

    types = pdt.collect_sqn_type_tuples('кетчуп томат')
    pt = ProductType('кетчуп', 'помидор')
    assert pt in types

def test_context_terms_full(pdt_full):
    try:
        rel = pdt_full.find_product_type_relations(u'продукт йогуртный перс/мар/ананас/дыня')
    except Exception as e:
        print(to_str(e))
        raise

    pt_mar_bad_parent = ProductType(u'продукт', u'мар')
    pt_mar = ProductType(u'продукт', u'йогуртный', u'мар')
    pt_mar_full = ProductType(u'продукт', u'йогуртный', u'маракуйя')
    eq_relation = pt_mar.equals_to(pt_mar_full, dont_change=True)

    assert pt_mar in rel
    assert pt_mar_bad_parent not in rel
    assert eq_relation in rel[pt_mar]


def test_dawg_persistence_full():
    print("test_dawg_persistence()")
    filename = 'out/_term_dict_test.dawg'
    test_term_dict_saved = dump_term_dict_from_product_types(None, filename)
    test_term_dict_loaded = load_term_dict(filename)
    max_id = test_term_dict_loaded.get_max_id()
    assert test_term_dict_saved.get_max_id() == max_id and max_id > 0, "Saved and loaded dawgs are different size!"
    for i in range(1, max_id + 1):
        term_saved = test_term_dict_saved.get_by_id(i)
        term_loaded = test_term_dict_loaded.get_by_id(i)
        assert isinstance(term_saved, TypeTerm) and isinstance(term_loaded, TypeTerm), \
            "Terms have bad type"
        assert term_saved is not term_loaded and term_saved == term_loaded and type(term_saved) == type(term_loaded), \
            "Saved and Loaded terms are different!"
    print("test_dawg_persistence(): success")
