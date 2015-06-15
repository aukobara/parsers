# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
from collections import defaultdict
from functools import wraps
import pytest

from ok.dicts import to_str, main_options
from ok.dicts.product import Product
from ok.dicts.product_type import ProductType
from ok.dicts.product_type_dict import reload_product_type_dict
from ok.dicts.russian import get_word_normal_form
from ok.dicts.term import load_term_dict, TypeTerm, ContextRequiredTypeTermException, dump_term_dict_from_product_types, \
    CompoundTypeTerm, ContextDependentTypeTerm, ctx_def, DEFAULT_CONTEXT, WithPropositionTypeTerm, TermContext, \
    context_aware


# noinspection PyUnresolvedReferences
@pytest.fixture(autouse=True)
def clear_terms_dict():
    TypeTerm.term_dict.clear()

# noinspection PyUnresolvedReferences
@pytest.fixture
def pdt():
    config = main_options(
        ['test.py', '-base-dir', 'resources\\test', '-in-product-types-json', 'product_types_test_mar.json'])
    _pdt = reload_product_type_dict(config)
    return _pdt

# noinspection PyUnresolvedReferences
@pytest.fixture
def pdt_full():
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
    assert term_main == 'перс маракуйя ананас дыня'
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
    prefix_ctx_terms = [TypeTerm.make('шокол'), TypeTerm.make('шоколадн')]
    t_base = TypeTerm.make('шок')
    t_norm = TypeTerm.make('шоколад')
    t_ctx = TypeTerm.make('батончик')

    for t in prefix_ctx_terms:
        assert isinstance(t, ContextDependentTypeTerm)
        with pytest.raises(ContextRequiredTypeTermException):
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


def test_context_terms_parse_ambigous_with_dict(pdt):
    types = pdt.collect_sqn_type_tuples(u'продукт мол-раст сгущ с сахаром сгущенка с кофе')

    pt_full = ProductType(u'продукт', u'молоко', u'сгущенка')
    pt_not_context = ProductType('продукт', 'растворимый', 'с кофе')
    pt_comp_context = ProductType('продукт', 'молоко', 'растворимый', 'с кофе')

    assert pt_full in types
    assert pt_not_context in types
    assert pt_comp_context in types

    with pytest.raises(ContextRequiredTypeTermException):
        pdt.collect_sqn_type_tuples(u'сгущ продукт мол-раст с сахаром сгущенка с кофе')


def test_compound_spaced_main_form():
    # Pepsi has known word_normal_form 'Pepsi-Cola'. That may produce recursion when calculate all spaced main form
    term = TypeTerm.make(u'пепси-кола')
    main_form = term.get_main_form()
    assert main_form == 'пепси кола'


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
