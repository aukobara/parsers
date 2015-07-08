# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
from collections import defaultdict, namedtuple, OrderedDict, deque
from functools import wraps
import re
import dawg
import itertools

from ok.dicts import to_str, main_options
from ok.dicts.russian import get_word_normal_form, is_known_word, is_simple_russian_word, RE_WORD_OR_NUMBER_CHAR_SET
from ok.utils import EventfulDict

TYPE_TERM_PROPOSITION_LIST = (u'в', u'во', u'с', u'со', u'из', u'для', u'и', u'на', u'без', u'к', u'не', u'де', u'по', u'под')
TYPE_TERM_PROPOSITION_AND_WORD_LIST = (u'со',)


class TypeTermException(Exception):
    pass


class ContextRequiredTypeTermException(TypeTermException):
    pass

# Context aware decorator
def context_aware(func):
    _context_aware_function_reg = getattr(context_aware, '_context_aware_function_reg', [])
    try:
        func_idx = _context_aware_function_reg.index(func)
    except ValueError:
        _context_aware_function_reg.append(func)
        context_aware._context_aware_function_reg = _context_aware_function_reg
        func_idx = len(_context_aware_function_reg) - 1

    @wraps(func)
    def wrapped(*args, **kwargs):
        assert len(args) <= 2 or 'context' in kwargs, "@context_aware method call must have context= named parameter " \
                                                      "if it has another arguments"
        term = args[0]
        assert isinstance(term, TypeTerm)

        context = None
        if term._is_context_required is None or term._is_context_required:
            if 'context' in kwargs:
                context = TermContext.ensure_context(kwargs.get('context'))
                kwargs['context'] = context
            elif len(args) == 2:
                context = TermContext.ensure_context(args[1])
                if type(context) != type(args[1]):
                    args = list(args)
                    args[1] = context
        if context:
            context_key = context.call_key(func_idx, term.term_id)
            result = context.cached_result(context_key)
            if result is None:
                context.mark_self(context_key)
                try:
                    result = func(*args, **kwargs)
                    context.cache_result(context_key, result)
                except ContextRequiredTypeTermException as cre:
                    context.cache_exception(context_key, cre)
                    raise
                finally:
                    context.unmark_self(context_key)
            return result
        return func(*args, **kwargs)

    wrapped.context_aware_index = func_idx
    return wrapped


class TypeTermDict(object):
    # Terms storage and dict. It should not be used directly and work through TypeTerm decorator methods.

    def __init__(self):
        self.__terms = defaultdict(set)
        """@type: dict of (unicode, int)"""
        self.__terms_dawg = dawg.BytesDAWG()
        self.__terms_idx = [None] * 10000
        """@type: list[unicode]"""
        self.__next_idx = 1  # 0 is not used to avoid matching with None

    def __term_to_idx(self, term):
        # Naive non-thread safe realization
        # If int - Tuple unfolding - referenced directly to indexes. Just return it
        if isinstance(term, int):
            idx = term
        elif isinstance(term, TypeTerm):
            idx = self.find_id_by_unicode(term)
            if idx is None:
                idx = self.__next_idx
                self.__terms_idx[idx] = term
                self.__terms[term] = idx
                self.__next_idx += 1
                if self.__next_idx == len(self.__terms_idx):
                    # Extend index storage
                    new_idx = [None] * (int(len(self.__terms_idx) * 1.75))
                    new_idx[:len(self.__terms_idx)] = self.__terms_idx[:]
                    self.__terms_idx = new_idx
        else:
            raise Exception("Only TypeTerms or int are accepted but %s is given" % type(term))
        return idx

    def find_id_by_unicode(self, term_str):
        term_str_uni = to_str(term_str)
        dawg_id_list = self.__terms_dawg.get(term_str_uni)
        term_id = self.__terms.get(term_str_uni) if not dawg_id_list else int(dawg_id_list[0])
        return term_id

    def clear(self):
        self.__terms = defaultdict(set)
        self.__terms_dawg = dawg.BytesDAWG()
        self.__terms_idx = [None] * 10000
        self.__next_idx = 1

    def update_dawg(self, skip_word_forms_validation=False):
        """
        Convert __terms dict to DAWG and clear. Search by prefixes can be used in DAWG only.
        All new terms will be saved in __terms only and not searchable by prefixes until next update_dawg()
        @param bool skip_word_forms_validation: if True, do not invalidate all word_forms. Use this if absolutely
                    confident that all word_forms are already loaded to term dict
        """
        if not skip_word_forms_validation:
            count_wf = 0
            key_set = set(self.__terms.keys())
            seen_set = set()
            while key_set > seen_set:
                # New terms can appear during word forms generation
                for term_str in key_set - seen_set:
                    # Ensure all word forms are initialized before moving to dawg. All terms in dawg must be immutable
                    term = self.get_by_unicode(term_str)
                    if isinstance(term, ContextDependentTypeTerm):
                        count_wf += len(term.all_context_word_forms())
                    else:
                        count_wf += len(term.word_forms(context=None, fail_on_context=False) or [])
                    seen_set.add(term_str)
                key_set = set(self.__terms.keys())

        # noinspection PyCompatibility
        new_dawg = dawg.BytesDAWG((to_str(k), bytes(v)) for k, v in
                                  itertools.chain(self.__terms_dawg.iteritems(), self.__terms.viewitems()))
        assert len(new_dawg.keys()) == len(self.__terms.keys()) + len(self.__terms_dawg.keys()), \
            "DAWG does not match to terms dict!"
        self.__terms_dawg = new_dawg
        self.__terms.clear()

        # TODO: invalidate PrefixTypeTerms, i.e. check they are still valid PrefixTypeTerm.
        # To pass full check they have to be recreated and converted to simple type if required
        assert not any(isinstance(self.get_by_unicode(key), PrefixTypeTerm) for key in self.__terms_dawg.keys()), \
            "TODO: INVALIDATE Prefix Types before merge them to DAWG"

    def dawg_checksum(self):
        if self.__terms:
            raise TypeTermException("DAWG was dynamically updated. Use update_dawg() first to persist terms")
        from zlib import adler32
        from io import BytesIO
        b = BytesIO()
        self.__terms_dawg.write(b)
        checksum = adler32(b.getvalue()) & 0xffffffff
        return checksum

    def save_term(self, term):
        return self.__term_to_idx(term)

    def get_by_id(self, term_id):
        """
        @param int term_id: Term ID
        @rtype: TypeTerm|None
        """
        return self.__terms_idx[term_id] if 0 < term_id < self.__next_idx else None

    def get_max_id(self):
        return self.__next_idx - 1

    def get_by_unicode(self, term_str):
        """
        @param unicode|TypeTerm term_str: term string
        @rtype: TypeTerm|None
        """
        term_id = self.find_id_by_unicode(term_str)
        return self.get_by_id(term_id) if term_id is not None else None

    def find_by_unicode_prefix(self, prefix, return_self=True, not_compound=True):
        """
        Find terms with specified prefix. NOTE: dawg must be updated before with terms to find.
        If prefix is existing term it will be returned as well.
        @param unicode|TypeTerm prefix: prefix string
        @param bool return_self: if False do not count term with name equal prefix, only longer terms are counted
        @param bool not_compound: Do not count compound terms by default because their string representation is
                        complicated
        @rtype: list[TypeTerm]
        """
        keys = self.__terms_dawg.keys(to_str(prefix))
        if not_compound:
            keys = [k for k in keys if not CompoundTypeTerm.is_valid_term_for_type(k)]
        return [term for key in keys if return_self or key != prefix
                for term in [self.get_by_unicode(key)] if not not_compound or not isinstance(term, CompoundTypeTerm)]

    def count_terms_with_prefix(self, prefix, count_self=True, not_compound=True):
        """
        Count terms with specified prefix. NOTE: dawg must be updated before with terms to find.
        If prefix is existing term it will be counted as well except count_self=False is specified.
        @param unicode|TypeTerm prefix: prefix string
        @param bool count_self: if False do not count term with name equal prefix, only longer terms are counted
        @param bool not_compound: Do not count compound terms by default because their string representation is
                        complicated
        @rtype: int
        """
        key = to_str(prefix)
        prefixed_keys = self.__terms_dawg.keys(key)
        if not_compound:
            prefixed_keys = [k for k in prefixed_keys if not CompoundTypeTerm.is_valid_term_for_type(k)]
        return len(prefixed_keys) - (1 if not count_self and key in self.__terms_dawg else 0)

    def print_stats(self):
        print('TypeTerm set stats:\r\n\tterms: %d\r\n\tterms(dawg): %d\r\n\tnext term index: %d' %
              (len(self.__terms), len(self.__terms_dawg.keys()), self.__next_idx))

    def to_file(self, filename, verbose=False):
        if verbose:
            print("Save current term_dict dawg to file: %s" % filename)
            if self.__terms:
                print("WARN: Non-dawg dict is NOT empty and will not be saved! Update DAWG first!")
        if self.__terms_dawg:
            self.__terms_dawg.save(filename)
        if verbose:
            print("Dumped %d terms to %s" % (len(self.__terms_dawg.keys()), filename))

    def from_file(self, filename, verbose=False, skip_word_forms_validation=False):
        """
        @param bool skip_word_forms_validation: see description in update_dawg()
        """
        if verbose:
            print("Load term_dict dawg from file: %s" % filename)
            if self.__terms:
                print("WARN: Non-dawg dict is NOT empty and will be lost!")
        self.clear()
        new_dawg = dawg.BytesDAWG()
        new_dawg.load(filename)
        term_id = 0
        # noinspection PyCompatibility
        for term_str, term_id in sorted(new_dawg.iteritems(), key=lambda _t: int(_t[1])):
            term_id = int(term_id)
            term = TypeTerm.make(term_str)
            assert term.term_id == term_id
        assert self.__next_idx == term_id + 1, "Internal index does not match to dawg data!"

        self.update_dawg(skip_word_forms_validation=skip_word_forms_validation)

        try:
            assert list(new_dawg.keys()) == list(self.__terms_dawg.keys()), \
                'DAWG must be renewed - code or/and keyword dicts were changed'
        except AssertionError:
            # Some debug info for assertion - print diff keys
            print('DAWG diff (new keys appeared during load):')
            print('\r\n'.join(sorted(set(self.__terms_dawg.keys()) - set(new_dawg.keys()))))
            raise

        if verbose:
            if skip_word_forms_validation:
                print("Word forms invalidation skipped")
            print("Loaded %d terms from %s" % (len(self.__terms_dawg.keys()), filename))

        return self


class TypeTerm(unicode):
    # Multi-variant string. It has main representation but also additional variants which can be used for
    # combinations. Typical example is compound words separated by hyphen.

    not_a_term_character_pattern = re.compile('[^%s]+' % RE_WORD_OR_NUMBER_CHAR_SET, re.U)

    __slots__ = ('_term_id', '_variants', '_do_not_pair', '_always_pair', '_word_forms', '_is_context_required')

    term_dict = TypeTermDict()

    def __new__(cls, *args):
        if args and isinstance(args[0], TypeTerm) and getattr(args[0], '_term_id', None) is not None:
            return args[0]
        self = unicode.__new__(cls, *args)
        """@type: TypeTerm"""
        if not cls.is_valid_term_for_type(self):
            raise TypeTermException(u"Invalid term for type %s. Use another class or .make() method. Term: %s" %
                                    (cls, to_str(self)))

        exist_term = cls.term_dict.get_by_unicode(self)
        if exist_term is not None:
            self = exist_term
        else:
            self._term_id = None
        return self

    def __init__(self, from_str=''):
        """
        @param unicode from_str: term string
        """
        super(TypeTerm, self).__init__(from_str)
        # Do not init already cached terms
        if self.is_new():

            # These fields override default rules (aka exceptions). If another term in these sets than it always cannot
            # pair or can pair regardless of logic and common sense. Probably later this goes away when logic of
            # term pair eligibility will be more sophisticated.
            self._do_not_pair = set()
            self._always_pair = set()

            # Other TypeTerm's which can replace this one or their near by meaning including term itself.
            # First in the list is always Term's Main Form
            # Mostly - synonyms. It is used for same-same word matching
            # If None it means word forms has not been initialized.
            self._word_forms = None
            self._is_context_required = None

            # Put term to cache and assign id
            self._term_id = self.term_dict.save_term(self)

    def is_new(self):
        return self._term_id is None

    @staticmethod
    def is_a_term(term_str):
        return term_str and bool(re.sub(TypeTerm.not_a_term_character_pattern, u'', term_str))

    @staticmethod
    def is_proposition(word):
        return word in TYPE_TERM_PROPOSITION_LIST

    @staticmethod
    def is_compound_term(terms_str):
        return bool(re.search(TypeTerm.not_a_term_character_pattern, terms_str))

    @staticmethod
    def is_proposition_and_word(word):
        # When term can be both proposition and regular word
        return word in TYPE_TERM_PROPOSITION_AND_WORD_LIST

    @classmethod
    def is_valid_term_for_type(cls, term_str):
        return cls.is_a_term(term_str) and not cls.is_compound_term(term_str)

    @property
    def term_id(self):
        return self._term_id

    @classmethod
    def get_by_id(cls, term_id):
        """
        @param int term_id: Term ID
        @rtype: TypeTerm|None
        """
        return cls.term_dict.get_by_id(term_id)

    @staticmethod
    def make(term_str):
        """
        Factory method returns TypeTerm instance of correct type.
        Type is determined by term_str using .is_valid_term_for_type() method of each known type.
        @param unicode|TypeTerm|int term_str: int considered as term_id (raise TypeTermException if not exist);
                TypeTerm returns as is if persistent; otherwise it is a term string
        @rtype: TypeTerm
        """
        if isinstance(term_str, TypeTerm) and not term_str.is_new():
            return term_str
        if isinstance(term_str, int):
            term = TypeTerm.get_by_id(term_str)
            if not term:
                raise TypeTermException("Term_id[%d] does not found" % term_str)
            return term
        term_str = to_str(term_str)
        term = TypeTerm.term_dict.get_by_unicode(term_str)
        if term:
            return term
        if ContextDependentTypeTerm.is_valid_term_for_type(term_str):
            term = ContextDependentTypeTerm(term_str)
        elif TagTypeTerm.is_valid_term_for_type(term_str):
            term = TagTypeTerm(term_str)
        elif PrefixTypeTerm.is_valid_term_for_type(term_str):
            try:
                term = PrefixTypeTerm(term_str)
            except TypeTermException:
                pass

        if not term:
            if CompoundTypeTerm.is_valid_term_for_type(term_str):
                try:
                    term = WithPropositionTypeTerm(term_str)
                except TypeTermException:
                    try:
                        term = AbbreviationTypeTerm(term_str)
                    except TypeTermException:
                        term = CompoundTypeTerm(term_str)

        if not term:
            term = TypeTerm(term_str)

        return term

    def get_main_form(self, context=None):
        """
        Return term with main ('normalized') form of this term. Main form is required for matching and indexing terms.
        Two terms with the same main form are considered as equal or replaceable (e.g. synonyms, different part of
        speech, words with proposition etc). Actually, they may be are not replaceable in natural language but in terms
        of terms matching they represent the same entity.
        However, some terms may require context to understand their meaning. These are e.g. omonimia terms and shortened
        words.
        @param TermContext|list[TypeTerm]|None context: list of other terms are met in the same context as this
        @rtype: TypeTerm
        @return: term with Main Form of this. It may be the same term if it is own main form.
        @raise ContextRequiredTypeTermException: if context is required to recognize Main Form and specified context is
                empty or not enough
        """

        main_form = self.word_forms(context=context, fail_on_context=True)[0]
        return main_form

    def is_compatible_with(self, another_term, context=None):
        """
        @param TypeTerm another_term: term can be in one context with self. Mainly, it checks that another_term is not a one form
                of self or produced term
        @param TermContext|None context: term context
        @return:
        """
        if another_term in self._always_pair:
            return True
        # Default logic - do not pair with self, own variants, and own synonyms, except it was declared as always_pair
        if another_term == self or another_term in self.word_forms(context=context, fail_on_context=True):
            return False
        # Even if pass default logic - do not pair anyway if declared as do_not_pair
        if another_term in self._do_not_pair:
            return False
        return True

    def always_pair(self, *cp):
        self._always_pair.update(cp)

    def do_not_pair(self, *dnp):
        self._do_not_pair.update(dnp)

    @context_aware
    def word_forms(self, context=None, fail_on_context=False):
        """
        Collect and return all known word forms including itself. Main form will be always first (i.e. if term itself
        is not a main form it can be not the first in the list). Word forms are cached once and never changes
        @param TermContext|list[TypeTerm|unicode]|None context: term context
        @param bool fail_on_context: if True raise ContextRequiredTypeTermException if context is not sufficient.
                    if False, return None instead of exception
        @rtype: list[TypeTerm]|None
        """
        if self._word_forms is None:
            try:
                result = self._collect_self_word_forms(context=None)
                # Context is not required and thus collected word forms may be cached
                self._word_forms = result[:]
                self._is_context_required = False
            except ContextRequiredTypeTermException:
                self._word_forms = [u'__nocache__']
                self._is_context_required = True
                if not context and fail_on_context:
                    raise

        if u'__nocache__' in self._word_forms:
            try:
                result = self._collect_self_word_forms(context=context)
            except ContextRequiredTypeTermException:
                if fail_on_context:
                    raise
                result = None
        else:
            result = self._word_forms[:]

        return result

    def is_context_required(self):
        if self._is_context_required is None:
            try:
                word_forms = self.__class__.word_forms
                if hasattr(word_forms, 'context_aware_index'):
                    # Take original not-context-wrapped method. Otherwise, we will got recursion
                    word_forms = getattr(context_aware, '_context_aware_function_reg')[word_forms.context_aware_index]

                # Call word_forms without context to check whether it fails
                word_forms(self, context=None, fail_on_context=True)
                self._is_context_required = False
            except ContextRequiredTypeTermException:
                self._is_context_required = True
        return self._is_context_required

    def _collect_self_word_forms(self, need_normal_form=True, context=None):
        """
        @param TermContext context: term context
        @param bool need_normal_form: If False do not try to transform term to normal form. E.g. it is required for
                terms where normal form has no sense and they normalize by their own - compounds, tags, numbers, etc
        @rtype: list[TypeTerm]
        """
        main_form_syn = None
        if need_normal_form:
            # Try to guess about normal form of word and treat it as synonym
            self_normal_form = get_word_normal_form(self, strict=True)
            if self != self_normal_form:
                main_form_syn = self_normal_form

        collected_forms = [self.make(main_form_syn)] if main_form_syn else []
        if self != main_form_syn:
            collected_forms.append(self)
        return collected_forms

    @staticmethod
    def parse_term_string(terms_str):
        """
        Parse long string of multiple terms and return list of TypeTerms with respectful types.
        Main processing here is compound terms with proposition detection. Proposition is added to next word(s) as well.
        Also 'and' proposition is processed. All other work is delegated to TypeTerm.make()
        @param unicode|ok.query.tokens.Query terms_str: string of terms
        @rtype: list[TypeTerm]
        """
        import ok.query as query
        words = query.parse_query(terms_str).tokens
        terms = []
        """@type: list[TypeTerm]"""
        buf = u''
        buf_count = 0
        for w in words:
            if TypeTerm.is_a_term(w):
                term = None
                if TypeTerm.is_proposition(w) and not buf:
                    buf = w  # join proposition to the next words
                    if TypeTerm.is_proposition_and_word(w):
                        # Some propositions can participate also as words (e.g. when char O is used instead of number 0)
                        # Add such propositions as simple word
                        terms.append(TypeTerm.make(w))
                    continue
                if buf:
                    if w == u'и':
                        # Ignore 'and' if already in proposition mode
                        continue

                    if TypeTerm.is_proposition(w):
                        # Break previous proposition sequence and start new
                        buf = w
                        buf_count = 0
                        if TypeTerm.is_proposition_and_word(w):
                            # See above comments about dual prop/word cases
                            terms.append(TypeTerm.make(w))
                        continue

                    term = TypeTerm.make(u'%s %s' % (buf, w))
                    buf_count += 1

                    if buf_count == 2:
                        buf = u''
                        buf_count = 0

                if not term:
                    term = TypeTerm.make(w)
                terms.append(term)
        if buf and buf_count == 0:
            terms.append(TypeTerm.make(buf))

        return list(OrderedDict.fromkeys(terms))  # Filter duplicates

    def as_string(self):
        return to_str(self)

    def __repr__(self):
        return '<%s>%s:%s' % (self.__class__.__name__, ('', '[context]')[self.is_context_required()], super(TypeTerm, self).__repr__())


class CompoundTypeTerm(TypeTerm):
    """
    Term consists of two other simple TypeTerms
    If sub-terms are separated by non-space than space separated variant will be added as variant
    NOTE: In common case it is not possible to determine the Main Form of compound term by its sub terms - all of them
    have same rights. Hence, compound term is the own main form. However, in particular cases, like proposition and
    abbreviation types - there may be clear what sub term is main. Thus, subclasses are override word form collection
    @type _sub_terms: list[TypeTerm]
    """

    @classmethod
    def is_valid_term_for_type(cls, term_str):
        return cls.is_a_term(term_str) and cls.is_compound_term(term_str)

    def _tokenize(self, max_split=0):
        tokens = re.split(self.not_a_term_character_pattern, self, maxsplit=max_split)
        return filter(len, tokens)

    def _filter_tokens(self, tokens):
        # This is for override logic of token processing
        return tokens

    def _validate_tokens(self, tokens):
        return tokens and (len(tokens) > 1 or tokens[0] != self)

    def _make_token_terms(self, tokens):
        token_terms = [self.make(token) for token in tokens]
        spaced_form = self._spaced_form = u' '.join(token_terms)
        if self != spaced_form and spaced_form not in token_terms:
            token_terms.append(self.make(spaced_form))
        return token_terms

    def __init__(self, from_str=''):
        """
        @param unicode from_str: term string
        """
        # Check that is a new instance creation to avoid re-initialization for cached instances
        if self.is_new():
            self._spaced_form = None
            tokens = self._tokenize()
            tokens = self._filter_tokens(tokens)
            if not self._validate_tokens(tokens):
                raise TypeTermException(u'This is not a %s: %s' % (type(self), to_str(self)))
            self._sub_terms = self._make_token_terms(tokens)
        super(CompoundTypeTerm, self).__init__(from_str)

    @property
    def sub_terms(self):
        return self._sub_terms[:]

    def is_compatible_with(self, another_term, context=None):
        if not super(CompoundTypeTerm, self).is_compatible_with(another_term, context=context):
            # Check override rules
            return False
        if any(not sub_term.is_compatible_with(another_term, context=context) for sub_term in self._sub_terms):
            return False
        return True

    @property
    def simple_sub_terms(self):
        """
        Return only simple sub terms, i.e. skip white spaces form, proposition form, etc
        Usually it is sequence of original tokens
        """
        return [st for st in self.sub_terms if not isinstance(st, CompoundTypeTerm)]

    def _collect_self_word_forms(self, need_normal_form=False, context=None):
        # If CompoundTypeTerm has spaced form different than itself it must go first as Main Form to match other
        # compound terms with different delimiters
        collected_forms = super(CompoundTypeTerm, self)._collect_self_word_forms(
            need_normal_form=need_normal_form, context=context)

        spaced_forms = self._collect_self_spaced_forms(context)

        if spaced_forms:
            if not collected_forms or collected_forms[0] != spaced_forms[0]:
                collected_forms = [spaced_forms[0]] + collected_forms
            if len(spaced_forms) > 1:
                collected_forms.extend(spaced_forms[1:])

        # sub_terms = self.simple_sub_terms
        # if len(sub_terms) > 1:
        #     joined_form = ''.join(sub_terms)
        #     if joined_form and joined_form != self:
        #         collected_forms.append(TypeTerm.make(joined_form))

        return collected_forms

    def _collect_self_spaced_forms(self, context, need_all_main_spaced=True):
        collected_forms = []
        if self._spaced_form != self and self._spaced_form not in collected_forms:
            collected_forms.append(TypeTerm.make(self._spaced_form))

        if need_all_main_spaced:
            tokens = self.simple_sub_terms[:]
            tokens_count = len(tokens)
            token_buf = [None] * tokens_count
            i = 0
            while i < tokens_count:
                if context is None and tokens[i].is_context_required():
                    context = TermContext.ensure_context(tokens)
                token_main_form = tokens[i].get_main_form(context=context)

                if isinstance(token_main_form, CompoundTypeTerm):
                    if token_main_form._spaced_form == self._spaced_form:
                        # Recursion - simple spaced form was processed already
                        # token_main_form = token
                        token_buf = []
                        break
                    else:
                        sub_terms = token_main_form.simple_sub_terms
                        if tokens[i] in sub_terms:
                            # Self contained main form like pepsi vs pepsi-cola
                            # Eat everything that will be added with spaced form
                            sub_terms_count = len(sub_terms)
                            first_idx = sub_terms.index(tokens[i])
                            last_idx = sub_terms_count - sub_terms[::-1].index(tokens[i]) - 1
                            j = i - 1
                            while j >= 0 and first_idx-(i-j) >= 0 and tokens[j] == sub_terms[first_idx-(i-j)]:
                                token_buf[j] = None
                                j -= 1
                            j = i
                            while j < tokens_count - 1 and last_idx+(j-i)+1 < sub_terms_count \
                                    and tokens[j+1] == sub_terms[last_idx+(j-i)+1]:
                                # Need to find last token covered by spaced form
                                j += 1
                            i = j
                        token_main_form = token_main_form._spaced_form
                token_buf[i] = token_main_form
                i += 1
            all_main_spaced_form = ' '.join(filter(bool, token_buf))
            if all_main_spaced_form and all_main_spaced_form != self:
                if not collected_forms or collected_forms[0] != all_main_spaced_form:
                    collected_forms = [TypeTerm.make(all_main_spaced_form)] + collected_forms

        return collected_forms


class WithPropositionTypeTerm(CompoundTypeTerm):
    """
    Special form of compound Term consists of proposition and other TypeTerms
    Proposition is not considered as sub-term when checking compatibility (aka stop-words)
    Proposition is considered as meaningful before terms with length more then two. Other cases should be treated as
    AbbreviationTypeTerm
    @type proposition: unicode
    """
    def __init__(self, from_str=''):
        """
        @param unicode from_str: term string
        """
        if self.is_new():
            self.proposition = None
        super(WithPropositionTypeTerm, self).__init__(from_str)

    def _tokenize(self, _=None):
        return super(WithPropositionTypeTerm, self)._tokenize(max_split=1)

    def _validate_tokens(self, tokens):
        comp_validate = super(WithPropositionTypeTerm, self)._validate_tokens(tokens)
        return comp_validate and self.proposition and any(len(t) > 2 for t in tokens)

    def _filter_tokens(self, tokens):
        tokens = super(WithPropositionTypeTerm, self)._filter_tokens(tokens)
        # Take first proposition only
        if tokens and self.is_proposition(tokens[0]):
            self.proposition = tokens.pop(0)
        return tokens

    def _make_token_terms(self, tokens):
        token_terms = super(WithPropositionTypeTerm, self)._make_token_terms(tokens)
        for term in token_terms[:]:
            if isinstance(term, CompoundTypeTerm):
                # Add proposition form to all sub terms as well as sub terms themselves
                for sub_term in term.sub_terms:
                    token_terms.append(sub_term)
                    token_terms.append(WithPropositionTypeTerm(u'%s %s' % (self.proposition, sub_term)))
        return token_terms

    def is_compatible_with(self, another_term, context=None):
        if not super(WithPropositionTypeTerm, self).is_compatible_with(another_term, context=context):
            return False
        if isinstance(another_term, WithPropositionTypeTerm):
            # Compatible terms cannot start with the same proposition
            if self.proposition == another_term.proposition:
                return False
        return True

    def _collect_self_word_forms(self, need_normal_form=False, context=None):
        # For proposition it is clear which sub-term represent Main Form - it has only one real sub-term
        collected_forms = super(WithPropositionTypeTerm, self)._collect_self_word_forms(
            need_normal_form=need_normal_form, context=context)

        main_form = self.sub_terms[0].get_main_form(context=context)
        if not collected_forms or main_form != collected_forms[0]:
            collected_forms = [main_form] + collected_forms
        return collected_forms

    def _collect_self_spaced_forms(self, context, need_all_main_spaced=False):
        collected_forms = super(WithPropositionTypeTerm, self)._collect_self_spaced_forms(context, need_all_main_spaced)

        main_form = self.sub_terms[0].get_main_form(context=context)
        collected_forms.append(TypeTerm.make(u'%s %s' % (self.proposition, main_form)))

        return collected_forms

class TagTypeTerm(TypeTerm):
    # Special term starting with hash - it is used for unparseable tag names
    @classmethod
    def is_valid_term_for_type(cls, term_str):
        return cls.is_a_term(term_str) and term_str.startswith(u'#')

    def as_string(self):
        return to_str(self.replace(u'#', ''))


class AbbreviationTypeTerm(CompoundTypeTerm):
    # Short form of compound term consists of abbreviation in one or multiple parts
    # Short sub-terms are not considered as separate terms and treated only as a whole with other sub-terms

    def _make_token_terms(self, tokens):
        sub_terms = super(AbbreviationTypeTerm, self)._make_token_terms(tokens)
        # Filter non simple terms or simple but long, i.e. meaningful
        result = []
        for st in sub_terms:
            if not TypeTerm.is_valid_term_for_type(st) or len(st) > 2:
                result.append(st)
        return result

    def _validate_tokens(self, tokens):
        comp_valid = super(AbbreviationTypeTerm, self)._validate_tokens(tokens)
        return comp_valid and (any(len(t) <= 2 for t in tokens))

    def _collect_self_word_forms(self, need_normal_form=False, context=None):
        # For abbreviation - special case exist when it is clear which sub-term represent Main Form -
        # when one only sub-term is long and can represent normal term.
        collected_forms = super(AbbreviationTypeTerm, self)._collect_self_word_forms(
            need_normal_form=need_normal_form, context=context)

        if len(self.simple_sub_terms) == 1:
            main_form = self.simple_sub_terms[0].get_main_form(context=context)
            if not collected_forms or main_form != collected_forms[0]:
                collected_forms = [main_form] + collected_forms
        return collected_forms


class PrefixTypeTerm(TypeTerm):
    # Short word that has more longer unique form

    @classmethod
    def is_valid_term_for_type(cls, term_str):
        simple_type_valid = super(PrefixTypeTerm, cls).is_valid_term_for_type(term_str)
        if not simple_type_valid or len(term_str) < 3:
            return False
        return cls.term_dict.count_terms_with_prefix(term_str, count_self=False) >= 1

    def _validate(self, prefixed_terms):
        """
        @param list[TypeTerm] prefixed_terms: terms with prefix
        @rtype: bool
        """
        common_main_form_term_id = -1
        valid = True
        for term in sorted(prefixed_terms, key=len, reverse=True):
            # TODO: word_forms of other terms prohibited during __init__ phase of term because it can cause recursion
            if self in term.word_forms():
                # Term is already form of another term. Hence, cannot be treated as independent term and should be
                # simple term instead
                valid = False
                break

            main_form_term_id = term.get_main_form().term_id
            if common_main_form_term_id < 0:
                common_main_form_term_id = main_form_term_id
            elif common_main_form_term_id != main_form_term_id:
                # Prefix can be detected for one term only with multiple forms
                valid = False
                break

        return valid

    def __init__(self, from_str=''):
        """
        @param unicode from_str: term string
        """
        # Check that is a new instance creation to avoid re-initialization for cached instances
        if self.is_new():
            prefixed_terms = [term for term in self.term_dict.find_by_unicode_prefix(self, return_self=False)]
            if not self._validate(prefixed_terms):
                raise TypeTermException(u'This is not a %s: %s' % (type(self), to_str(self)))
            self._prefixed_terms = prefixed_terms
        super(PrefixTypeTerm, self).__init__(from_str)

    def _collect_self_word_forms(self, need_normal_form=False, context=None):
        collected_forms = super(PrefixTypeTerm, self)._collect_self_word_forms(
            need_normal_form=need_normal_form, context=context)

        main_form_term = self._prefixed_terms[0].get_main_form(context=context)
        collected_forms.extend(self._prefixed_terms)

        if main_form_term and (not collected_forms or collected_forms[0] != main_form_term):
            collected_forms = [main_form_term] + collected_forms

        return collected_forms

ctx_def = namedtuple('_ctx_def', 'ctx_terms main_form')
DEFAULT_CONTEXT = u'__default__'

class ContextDependentTypeTerm(TypeTerm):

    # If any term in context of ctx_terms use main_form
    ctx_dependent_terms = EventfulDict({
        # Very often cross-dep. TODO: Check cross-dependencies - e.g. шок <-> мол, шок <-> нач
        'шок': [ctx_def(['глазурь', 'конфеты', 'крем', 'молочный', 'мороженое', 'пломбир', 'батончик', 'начинка'], 'шоколадный')],
        'гор': [ctx_def(['шоколад'], 'горький')],
        'мол': [ctx_def(['десерт', 'каша', 'коктейль', 'конфеты', 'крем', 'напиток', 'продукт', 'сыворотка', 'шоколад'], 'молочный'),
                ctx_def(['кофе'], 'молотый')],
        'молоч': [ctx_def([DEFAULT_CONTEXT], 'молочный')],
        'прод': [ctx_def(['десерт', 'каша', 'молочный'], 'продукт')],
        'нач': [ctx_def(['шоколад', 'подушечки', 'булочка', 'рулет', 'выпечка', 'хлебобулочный'], 'начинка')],

        # 2+ values variants
        'раст': [ctx_def(['кофе'], 'растворимый'),
                 ctx_def(['крем', 'мороженое'], 'растительный')],
        'биф': [ctx_def(['кефир'], 'бифидо'),
                ctx_def(['помидор'], 'биф')],
        'мин': [ctx_def(['вода'], 'минеральная'),
                ctx_def(['йогурт'], 'витамин')],
        'слив': [ctx_def(['масло', 'начинка', 'маргарин'], 'сливочный'),
                 ctx_def(['компот'], 'слива')],
        'сливоч': [ctx_def([DEFAULT_CONTEXT], 'сливочный')],
        'гл': [ctx_def(['мороженое', 'шоколад'], 'глазурь'),
               ctx_def([DEFAULT_CONTEXT], 'гл')],
        'глаз': [ctx_def(['мороженое', 'пломбир', 'шоколад'], 'глазурь'),
                 ctx_def([DEFAULT_CONTEXT], 'глаз')],
        'глазир': [ctx_def([DEFAULT_CONTEXT], 'глазированный')],
        'кат': [ctx_def(['1', '2', 'баранина', 'бройлеры', 'говядина', 'гуси', 'индейки', 'конина', 'оленина', 'телятина', 'цыплята'], 'категории'),
                ctx_def(['конфеты'], 'кат')],
        'морс': [ctx_def(['соль', 'рыба'], 'морской'),
                 ctx_def([DEFAULT_CONTEXT], 'морс')],

        # one-value variants
        'ст': [ctx_def(['горчица', 'желе', 'йогурт', 'кофе', 'соус', 'кетчуп', 'цикорий'], 'стекло')],
        'осв': [ctx_def(['нектар', 'сок'], 'осветленный')],
        'туш': [ctx_def(['говядина', 'суп', 'свинина', 'мясо'], 'тушеная')],
        'потр': [ctx_def(['горбуша', 'форель', 'минтай', 'рыба'], 'потрошеная')],
        'крупн': [ctx_def(['чай'], 'крупнолистовой')],
        'хв': [ctx_def(['креветки'], 'хвост')],
        'вар': [ctx_def(['докторская', 'колбаса', 'молочная', 'сгущёнка'], 'вареная')],
        'серв': [ctx_def(['колбаса'], 'сервелат')],
        'жар': [ctx_def(['арахис', 'картофель', 'лук', 'пюре'], 'жаренный')],
        'пш': [ctx_def(['хлопья'], 'пшеничные')],
        'пшенич': [ctx_def([DEFAULT_CONTEXT], 'пшеничные')],
        'гот': [ctx_def(['завтрак'], 'готовый')],
        'цел': [ctx_def(['шоколад', 'молоко', 'конфеты', 'кондитерский'], 'цельный')],
        'цельн': [ctx_def([DEFAULT_CONTEXT], 'цельный')],
        'раф': [ctx_def(['масло'], 'рафинированное')],
        'подсол': [ctx_def(['масло','семечки'], 'подсолнечное')],
        'сод': [ctx_def(['напиток', 'сок'], 'содержащий')],
        'содер': [ctx_def([DEFAULT_CONTEXT], 'содержащий')],
        'пит': [ctx_def(['вода', 'йогурт'], 'питьевой')],
        'сл': [ctx_def(['напиток', 'вода'], 'слабо')],
        'леч': [ctx_def(['вода'], 'лечебная')],
        'пос': [ctx_def(['сельдь'], 'посол')],
        'сп': [ctx_def(['сельдь'], 'специальный')],
        'спец': [ctx_def([DEFAULT_CONTEXT], 'специальный')],
        'корн': [ctx_def(['салат'], 'корн')],
        'том': [ctx_def(['сок'], 'томатный')],
        'фарш': [ctx_def([DEFAULT_CONTEXT], 'фарш'), ctx_def(['оливки'], 'фаршированные')],
        'пл': [ctx_def([DEFAULT_CONTEXT], 'плавленный'), ctx_def(['мороженое'], 'пломбир')],

        # Default only - abbreviations and synonyms
        'стер': [ctx_def([DEFAULT_CONTEXT], 'стерилизованный')],
        'сильногаз': [ctx_def([DEFAULT_CONTEXT], 'сильногазированный')],
        'кус': [ctx_def([DEFAULT_CONTEXT], 'кусок')],
        'сокосод': [ctx_def([DEFAULT_CONTEXT], 'сокосодержащий')],
        'подкопч': [ctx_def([DEFAULT_CONTEXT], 'подкопченный')],
        'среднегаз': [ctx_def([DEFAULT_CONTEXT], 'среднегазированный')],
        'сокосодер': [ctx_def([DEFAULT_CONTEXT], 'сокосодержащий')],
        'пастер': [ctx_def([DEFAULT_CONTEXT], 'пастеризованный')],
        'сол': [ctx_def([DEFAULT_CONTEXT], 'соленый')],
        'растит': [ctx_def([DEFAULT_CONTEXT], 'растительный')],
        'раств': [ctx_def([DEFAULT_CONTEXT], 'растворимый')],
        'обог': [ctx_def([DEFAULT_CONTEXT], 'обогащенный')],
        'биопрод': [ctx_def([DEFAULT_CONTEXT], 'биопродукт')],
        'кеф': [ctx_def([DEFAULT_CONTEXT], 'кефир')],
        'двухсл': [ctx_def([DEFAULT_CONTEXT], 'двухслойный')],
        'молсод': [ctx_def([DEFAULT_CONTEXT], 'молокосодержащий')],
        'молокосод': [ctx_def([DEFAULT_CONTEXT], 'молокосодержащий')],
        'твор': [ctx_def([DEFAULT_CONTEXT], 'творог')],
        'творож': [ctx_def([DEFAULT_CONTEXT], 'творожный')],
        'кисломол': [ctx_def([DEFAULT_CONTEXT], 'кисломолочный')],
        'аром': [ctx_def([DEFAULT_CONTEXT], 'аромат')],
        'ультрапаст': [ctx_def([DEFAULT_CONTEXT], 'ультрапастеризованный')],
        'вит': [ctx_def([DEFAULT_CONTEXT], 'витамин')],
        'питьев': [ctx_def([DEFAULT_CONTEXT], 'питьевой')],
        'сгущ': [ctx_def([DEFAULT_CONTEXT], 'сгущёнка')],
        'зернен': [ctx_def([DEFAULT_CONTEXT], 'зерненный')],
        'зам': [ctx_def([DEFAULT_CONTEXT], 'замороженный')],
        'рж': [ctx_def([DEFAULT_CONTEXT], 'ржаной')],
        'нат': [ctx_def([DEFAULT_CONTEXT], 'натуральный')],
        'натр': [ctx_def([DEFAULT_CONTEXT], 'натрий')],
        'низкокал': [ctx_def([DEFAULT_CONTEXT], 'низкокалорийный')],
        'клуб': [ctx_def([DEFAULT_CONTEXT], 'клубника')],
        'обж': [ctx_def([DEFAULT_CONTEXT], 'обжаренный')],
        'бальзамич': [ctx_def([DEFAULT_CONTEXT], 'бальзамический')],
        'суш': [ctx_def([DEFAULT_CONTEXT], 'сушеный')],
        'сочн': [ctx_def([DEFAULT_CONTEXT], 'сочный')],
        'прес': [ctx_def([DEFAULT_CONTEXT], 'прессованный')],
        'сах': [ctx_def([DEFAULT_CONTEXT], 'сахар')],

        # Update 25062016 - semi-auto-generated
        'газ': [ctx_def([DEFAULT_CONTEXT], 'газированный')],
        'белк': [ctx_def([DEFAULT_CONTEXT], 'белковый')],
        'перс': [ctx_def([DEFAULT_CONTEXT], 'персик')],
        'асс': [ctx_def([DEFAULT_CONTEXT], 'ассортимент')],
        'атл': [ctx_def([DEFAULT_CONTEXT], 'атлантический')],
        'бакл': [ctx_def([DEFAULT_CONTEXT], 'баклажан')],
        'ваф': [ctx_def([DEFAULT_CONTEXT], 'вафля')],
        'вял': [ctx_def([DEFAULT_CONTEXT], 'вяленый')],
        'доб': [ctx_def([DEFAULT_CONTEXT], 'добавление')],
        'кож': [ctx_def([DEFAULT_CONTEXT], 'кожа')],
        'осн': [ctx_def([DEFAULT_CONTEXT], 'основа')],
        'охл': [ctx_def([DEFAULT_CONTEXT], 'охлаждённый')],
        'пив': [ctx_def([DEFAULT_CONTEXT], 'пиво')],
        'рыб': [ctx_def([DEFAULT_CONTEXT], 'рыба')],
        'ябл': [ctx_def([DEFAULT_CONTEXT], 'яблоко')],
        'ветч': [ctx_def([DEFAULT_CONTEXT], 'ветчина')],
        'вишн': [ctx_def([DEFAULT_CONTEXT], 'вишня')],
        'возд': [ctx_def([DEFAULT_CONTEXT], 'воздух')],
        'конв': [ctx_def([DEFAULT_CONTEXT], 'конверт')],
        'конц': [ctx_def([DEFAULT_CONTEXT], 'концентрат')],
        'мекс': [ctx_def([DEFAULT_CONTEXT], 'мексиканский')],
        'минд': [ctx_def([DEFAULT_CONTEXT], 'миндаль')],
        'морк': [ctx_def([DEFAULT_CONTEXT], 'морковь')],
        'мясн': [ctx_def([DEFAULT_CONTEXT], 'мясной')],
        'очищ': [ctx_def([DEFAULT_CONTEXT], 'очищенный')],
        'прир': [ctx_def([DEFAULT_CONTEXT], 'природа')],
        'рифл': [ctx_def([DEFAULT_CONTEXT], 'рифленый')],
        'стак': [ctx_def([DEFAULT_CONTEXT], 'стакан')],
        'топл': [ctx_def([DEFAULT_CONTEXT], 'топлёный')],
        'цейл': [ctx_def([DEFAULT_CONTEXT], 'цейлон')],
        'шлиф': [ctx_def([DEFAULT_CONTEXT], 'шлифование')],
        # Unknown
        'уп': [ctx_def([DEFAULT_CONTEXT], 'упаковка')],
        'зол': [ctx_def([DEFAULT_CONTEXT], 'золото')],
        'йог': [ctx_def([DEFAULT_CONTEXT], 'йогурт')],
        'йодир': [ctx_def([DEFAULT_CONTEXT], 'йодированный')],
        'панир': [ctx_def([DEFAULT_CONTEXT], 'панировка')],
        'сухар': [ctx_def([DEFAULT_CONTEXT], 'сухарь')],
        'трост': [ctx_def([DEFAULT_CONTEXT], 'тростник')],
        'алк': [ctx_def([DEFAULT_CONTEXT], 'алкогольный')],
        'безалк': [ctx_def([DEFAULT_CONTEXT], 'безалкогольный')],
        'картоф': [ctx_def([DEFAULT_CONTEXT], 'картофельный')],
        'пригот': [ctx_def([DEFAULT_CONTEXT], 'приготовления')],
        'делик': [ctx_def([DEFAULT_CONTEXT], 'деликатесный')],
        'итал': [ctx_def([DEFAULT_CONTEXT], 'итальянский')],
        'сыв': [ctx_def([DEFAULT_CONTEXT], 'сыворотка')],
        'чернопл': [ctx_def([DEFAULT_CONTEXT], 'черноплодный')],
        'неразд': [ctx_def([DEFAULT_CONTEXT], 'неразделанный')],
        'хруст': [ctx_def([DEFAULT_CONTEXT], 'хрустящий')],
        'лес': [ctx_def([DEFAULT_CONTEXT], 'лесной')],
        'имит': [ctx_def([DEFAULT_CONTEXT], 'имитированный')],
        'суб': [ctx_def(['кофе'], 'сублимированный')],
        'зел': [ctx_def([DEFAULT_CONTEXT], 'зеленый')],

    })
    # Test definition - is used in smoke tests
    ctx_dependent_terms.update({u'мар': [ctx_def(['йогурт', 'напиток'], 'маракуйя')]})

    ctx_dependent_full_terms = ctx_triggers = None
    _last_ctx_dependent_terms_version = ctx_dependent_terms.version - 1

    @classmethod
    def ensure_full_terms_index(cls):
        if cls._last_ctx_dependent_terms_version == cls.ctx_dependent_terms.version:
            # Index is up-to-date
            return
        # Reverse index for search by prefix
        cls.ctx_dependent_full_terms = dawg.BytesDAWG(
            (ctx.main_form, key.encode('utf-8')) for key, ctx_defs in cls.ctx_dependent_terms.viewitems() for ctx in ctx_defs)
        cls.ctx_triggers = {trigger_term for key, ctx_defs in cls.ctx_dependent_terms.viewitems() for ctx in ctx_defs
                            for trigger_term in ctx.ctx_terms} - {DEFAULT_CONTEXT}
        cls._last_ctx_dependent_terms_version = cls.ctx_dependent_terms.version

    ctx_dependent_terms.after_change(lambda: ContextDependentTypeTerm.ensure_full_terms_index())

    _context_log_enabled = False

    @classmethod
    def is_valid_term_for_type(cls, term_str):
        simple_valid = super(ContextDependentTypeTerm, cls).is_valid_term_for_type(term_str)
        return simple_valid and (term_str in cls.ctx_dependent_terms or cls.is_valid_term_for_prefix(term_str))

    @classmethod
    def is_valid_term_for_prefix(cls, term_str):
        cls.ensure_full_terms_index()

        if len(term_str) <= 2 or term_str in cls.ctx_dependent_terms or term_str in cls.ctx_dependent_full_terms \
                or term_str in cls.ctx_triggers:
            return False
        # noinspection PyCompatibility
        found = any(term_str.startswith(key.decode('utf-8')) and term_str != get_word_normal_form(full_term)
                    for full_term, key in cls.ctx_dependent_full_terms.iteritems(to_str(term_str)))
        return found

    def __init__(self, from_str=''):
        """@param unicode from_str: term string"""
        if self.is_new():
            self._ctx_map = None
            """@type: dict of (TypeTerm|unicode, TypeTerm)"""
            self._last_ctx_dependent_terms_version = self.ctx_dependent_terms.version - 1
            self._ctx_map_hints = defaultdict(list)
            """@type: dict of (TypeTerm, list[tuple[TypeTerm])]"""
            self._context_log = set()
            self._prefix_base_key = None
        super(ContextDependentTypeTerm, self).__init__(from_str)

    def get_ctx_map(self):
        """@rtype: dict of (TypeTerm|unicode, TypeTerm)"""
        if self._ctx_map is None or self._last_ctx_dependent_terms_version != self.ctx_dependent_terms.version:
            ctx_map = dict()

            base_term = self.get_prefix_base_key()
            if base_term is not None:
                # Prefix term may have simplified context. Take only context definitions where prefix is part of full term
                prefix_ctx_defs = [pref_def for pref_def in self.ctx_dependent_terms[base_term] if pref_def.main_form.startswith(self)]
                if len(self) >= 5:
                    # For long prefix it is ~100% term equals to full term
                    # Simplify context to default form and assert it matches one full term only
                    full_terms = {pref_def.main_form for pref_def in prefix_ctx_defs}
                    if len(full_terms) == 1:
                        prefix_ctx_defs = [ctx_def([DEFAULT_CONTEXT], next(iter(full_terms)))]
                assert prefix_ctx_defs
                ctx_defs = prefix_ctx_defs
            else:
                ctx_defs = self.ctx_dependent_terms[self]
                """@type: list[ctx_def]"""

            for ctx_def_item in ctx_defs:
                # In default definitions term may be returned as is
                main_form_term = self if ctx_def_item.main_form == self else TypeTerm.make(get_word_normal_form(ctx_def_item.main_form))
                for ctx_term_str in ctx_def_item.ctx_terms:
                    if ctx_term_str == DEFAULT_CONTEXT:
                        ctx_map[DEFAULT_CONTEXT] = main_form_term
                    else:
                        if ContextDependentTypeTerm.is_valid_term_for_type(ctx_term_str) or \
                                (main_form_term != self and isinstance(main_form_term, ContextDependentTypeTerm)):
                            raise TypeTermException(
                                "ContextDependent term's [%s] context cannot be defined using another "
                                "ContextDependent term: %s" %
                                (self, ctx_term_str))
                        if CompoundTypeTerm.is_valid_term_for_type(ctx_term_str):
                            raise TypeTermException(
                                "ContextDependent term's [%s] context cannot be defined using compound terms: %s" %
                                (self, ctx_term_str))

                        ctx_term = TypeTerm.make(ctx_term_str)
                        ctx_map[ctx_term.get_main_form(context=None)] = main_form_term
            self._ctx_map = ctx_map
            self._last_ctx_dependent_terms_version = self.ctx_dependent_terms.version
        return self._ctx_map

    def is_prefix(self):
        return self.is_valid_term_for_prefix(self)

    def get_prefix_base_key(self):
        """@rtype: ContextDependentTypeTerm"""
        if self._prefix_base_key is None:
            if not self.is_prefix():
                return None
            self.ensure_full_terms_index()
            # noinspection PyCompatibility
            keys = [key.decode('utf-8') for full_term, key in self.ctx_dependent_full_terms.iteritems(to_str(self))
                    if self.startswith(key.decode('utf-8'))]
            longest_key = None
            for key in sorted(keys):
                # Keys are different! Assertion fails due to ambiguity
                assert not longest_key or key.startswith(longest_key), "Attempt to find base key in ambiguous context!"
                longest_key = key

            base_term = TypeTerm.make(longest_key)
            assert isinstance(base_term, ContextDependentTypeTerm)
            self._prefix_base_key = base_term
        return self._prefix_base_key

    @context_aware
    def get_main_form(self, context=None):
        """
        Look if specified terms in context match one of pre-defined context definitions and return known main form
        if found. If context is not enough (no one definition found) or more than one variant found - raise exception.
        For some terms may be defined default main form. It will be returned if no one term in context is matched.
        If context is empty and no default definition for only value - raise exception anyway. It can be used to check
        if term is really context dependent
        (pass None or empty context) to cache return value in callers for context-independent terms only.
        @param TermContext|list[TypeTerm|unicode] context: list of other terms are met in the same context as this
        @rtype: TypeTerm
        @raise ContextRequiredTypeTermException: 1) If empty or None context specified; 2) if context provided
                is not enough to resolve ambiguity and default context is not defined
        """

        if self._context_log_enabled and context:
            self._context_log.add(frozenset(context))

        ctx_map = self.get_ctx_map()
        values_variants = set(ctx_map.values()) - {ctx_map.get(DEFAULT_CONTEXT)}
        """@type: set[unicode]"""

        main_form = None
        """@type: TypeTerm|None"""
        ctx_term_match = None
        ctx_term_match_main_form = None
        hint_match = None
        hint_ctx_term_match = None

        if not main_form and values_variants:
            # Check if there is still something unclear. If only default value is present, than just go to default
            # section

            if not context:
                raise ContextRequiredTypeTermException("ContextDependent term with ambiguity must have context always:"
                                                       " %s" % self)

            if len(values_variants) == 1:
                # Fast track for optimization. If context has known terms in simple form and one variant of
                # values is available, than just go forward w/o cycle through all terms
                for ct in context:
                    main_form = ctx_map.get(ct)
                    if not main_form:
                        hints = self._ctx_map_hints.get(ct, [])
                        for hint in hints:
                            if all(hint[i] in context for i in range(len(hint)-1)):
                                ct_main = hint[-1]
                                main_form = ctx_map.get(ct_main)
                                if main_form:
                                    hint_ctx_term_match = ct
                                    hint_match = hint
                                    # print("Hint match: %s, %s, %s, %s" % (self, ct, to_str(hint), main_form))
                                    break
                    else:
                        ctx_term_match = ct
                    if main_form:
                        values_variants.pop()
                        break

            if not main_form and context.hints:
                for ct in context:
                    for hint in context.hints.get(ct, []):
                        if all(hint[i] in context for i in range(len(hint)-1)):
                            if hint[-1] in ctx_map:
                                self._ctx_map_hints[ct].append(hint)
                                # print("Ctx_map: %s, %s, %s" % (self, ct, to_str(hint)))

            if values_variants:
                for ctx_term in context:
                    if ctx_term == self:
                        continue

                    if ctx_term in ctx_map or not isinstance(ctx_term, TypeTerm):
                        # Shorthand optimization check to avoid heavy calls if anything clear and simple
                        ctx_term_main_form = ctx_term
                    else:
                        try:
                            ctx_term_main_form = ctx_term.get_main_form(context)
                        except ContextRequiredTypeTermException:
                            # ctx_term depends on this term or cannot be resolved.
                            # Anyway it's useless now - skip
                            continue

                    if main_form is None:
                        main_form = ctx_map.get(ctx_term_main_form)
                        ctx_term_match = ctx_term
                        ctx_term_match_main_form = ctx_term_main_form

                        if main_form:
                            values_variants.remove(main_form)
                            if not values_variants:
                                # No more ambiguity. Result has been found
                                break
                            if ctx_term in context.priority_terms:
                                # First term in context has top priority.
                                break
                    else:
                        # Check ambiguity for multi-variants
                        another_variant = ctx_map.get(ctx_term_main_form)
                        if another_variant and another_variant != main_form:
                            raise ContextRequiredTypeTermException(
                                'Context is too ambiguous: many variants for one term detected: '
                                '%s: 1) %s => %s; 2) %s => %s. Context: %s' %
                                (self, ctx_term_match, main_form, ctx_term, another_variant, u' + '.join(context)))

        if main_form and not values_variants:
            if ctx_term_match:
                # Tell context about match combination to let other terms use it as prediction
                # Avoid ambiguity terms because they can change match if other term come
                context.hint(self, ctx_term_match, main_form)
                if ctx_term_match_main_form and ctx_term_match_main_form != ctx_term_match:
                    context.hint(self, ctx_term_match_main_form, main_form)
            elif hint_match:
                context.hint(self, hint_ctx_term_match, main_form, hint_match)

        if not main_form:
            # Check if term accept default context
            main_form = ctx_map.get(DEFAULT_CONTEXT)
        if not main_form:
            raise ContextRequiredTypeTermException(u'Cannot find definition for context dependent term "%s". '
                                                   u'Context: %s' %
                                                   (self, u' + '.join(context or [u'<empty>'])))

        return main_form

    def word_forms(self, context=None, fail_on_context=True):
        try:
            main_form = self.get_main_form(context=context)
            collected_forms = []
            if main_form != self:
                collected_forms = main_form.word_forms(context)
            collected_forms.append(self)
        except ContextRequiredTypeTermException:
            if fail_on_context:
                raise
            collected_forms = None

        return collected_forms

    def all_context_word_forms(self):
        collected_word_forms = {self}
        ctx_map = self.get_ctx_map()
        # Check if main_form in definition is self (acceptable for default context definition)
        # If not all other terms must not be context dependant
        # For prefixes check their base key
        base_key = self.get_prefix_base_key()
        [collected_word_forms.update([main_form] if main_form == self or main_form == base_key else main_form.word_forms(context=None))
                                        for main_form in ctx_map.values()]
        return list(collected_word_forms)

    def all_context_main_forms(self):
        """@rtype: list[TypeTerm]"""
        collected_main_forms = set()
        ctx_map = self.get_ctx_map()
        # Check if main_form in definition is self (acceptable for default context definition)
        # If not all other terms must not be context dependant
        # For prefixes check their base key
        base_key = self.get_prefix_base_key()
        [collected_main_forms.add(main_form if main_form == self or main_form == base_key else main_form.get_main_form(context=None))
                                    for main_form in ctx_map.values()]
        return list(collected_main_forms)

class TermContext(deque):

    def __init__(self, iterable=None, not_a_terms=None, keep_original=False):
        super(TermContext, self).__init__(iterable)
        self.not_a_terms = set(not_a_terms or [])
        self.original_context = None if not keep_original else iterable if isinstance(iterable, TermContext) else list(iterable)
        # Terms will have priority if ambiguity is detected
        self.priority_terms = set()

        self._marked_as_self = set()

        self.result_cache = dict()
        """@type dict of (int, Any)"""
        self._cache_stamp = 0

        self.hints = defaultdict(list)
        """@type dict of (TypeTerm, list[tuple[TypeTerm])]"""

        if iterable:
            if isinstance(iterable, TermContext):
                self.not_a_terms |= iterable.not_a_terms
                self.result_cache = iterable.result_cache
                self.priority_terms = set(iterable.priority_terms)
                self._marked_as_self = set(iterable._marked_as_self)
                # All terms were already prepared in original term context
            else:
                # TODO: make this lazy on demand
                for i, t in enumerate(iterable):
                    if i == 0:
                        self.priority_terms.add(t)

                    if not isinstance(t, TypeTerm) and t not in self.not_a_terms:
                        try:
                            t = TypeTerm.make(t)
                            # Replace with term object version
                            self[i] = t
                        except TypeTermException:
                            # Bad term or is not a term - use as is
                            self.not_a_terms.add(t)
                            continue

                    if isinstance(t, CompoundTypeTerm):
                        # Extend context with compound terms sub-terms
                        self.extend(t.simple_sub_terms)
                        if t in self.priority_terms:
                            self.priority_terms.update(t.simple_sub_terms)

    @classmethod
    def ensure_context(cls, context):
        if context is None:
            return None
        if not isinstance(context, TermContext):
            context = cls(context)
        return context

    @staticmethod
    def call_key(method, term_id):
        return method * 100000 + term_id

    def mark_self(self, context_key):
        if context_key in self._marked_as_self:
            raise ContextRequiredTypeTermException(
                "Term is already marked as self, recursion's been detected")
        self._marked_as_self.add(context_key)
        return self

    def unmark_self(self, context_key):
        assert context_key in self._marked_as_self, "Previous context mark is not a term: %s" % context_key
        self._marked_as_self.remove(context_key)
        return self

    def is_marked_as_self(self, context_key):
        return context_key in self._marked_as_self

    @staticmethod
    def _extend_context(new_context, new_terms, old_context=None):
        """
        @param TermContext new_context: context to modify
        @param list[TypeTerm|unicode] new_terms: term list to add
        @param TermContext|None old_context: context to verify. if None verify in new_context
        """
        if old_context is None:
            old_context = new_context
        new_terms = OrderedDict.fromkeys(new_terms).keys()  # filter out dup terms
        new_context.extend([t for t in new_terms if t not in old_context])

    def clone(self):
        return TermContext(self, not_a_terms=self.not_a_terms)

    def cached_result(self, context_key):
        result = self.result_cache.get(context_key)
        if isinstance(result, ContextRequiredTypeTermException):
            if getattr(result, '__cache_stamp', -1) < self._cache_stamp:
                # New keys has been added to cache - need to refresh ones raised context exceptions
                self.result_cache[context_key] = None
                result = None
            else:
                raise result
        return result

    def cache_result(self, context_key, result):
        self._cache_stamp += 1
        self.result_cache[context_key] = result

    def cache_exception(self, context_key, exc):
        setattr(exc, '__cache_stamp', self._cache_stamp)
        self.result_cache[context_key] = exc

    def hint(self, term, ctx_term_match, main_form, hint_match=None):
        # print("Hint: %s, %s, %s, %s" % (term, ctx_term_match, main_form, to_str(hint_match)))
        if hint_match:
            self.hints[term].append(tuple([ctx_term_match] + list(hint_match[:-1]) + [main_form]))
        else:
            self.hints[term].append((ctx_term_match, main_form))


def print_prefix_word_candidates():
    term_dict = TypeTerm.term_dict
    prefix_terms = {}
    for i in range(1, term_dict.get_max_id() + 1):
        term = term_dict.get_by_id(i)
        if len(term) < 2 or type(term) != TypeTerm or not is_simple_russian_word(term):
            continue
        full_terms = [_t for _t in term_dict.find_by_unicode_prefix(term, return_self=False) if type(_t) == TypeTerm]
        if full_terms:
            if any(term in _t.word_forms() or term.get_main_form() in _t.word_forms() for _t in full_terms):
                continue
            # if len(full_terms) == 1)
            #     or not any(_t.get_main_form() != full_terms[0].get_main_form() for _t in full_terms[1:]):
            prefix_terms[term] = full_terms
    seen = set()

    print("=" * 80)
    print("3-4 char or unknown (almost) same main form and count>2")
    exclude = ['лен', 'мир', 'фри', 'вино', 'грей', 'карт', 'море']
    for term, full_terms in sorted(prefix_terms.items(), key=lambda _k:'%2d%s' % (len(_k[0]), _k[0])):
        if (len(term) not in [3, 4] and is_known_word(term)) or len(full_terms) < 2 or term in exclude:
            continue
        main_forms = defaultdict(set)
        [main_forms[full_term.get_main_form()].add(full_term) for full_term in full_terms]
        mf_lens = tuple(sorted(map(len, main_forms.values())))
        len_ft = len(full_terms)
        if mf_lens in {(len_ft,), (1, len_ft-1)} - {(1, 1)}:
            main_form = max(main_forms, key=lambda _mf: len(main_forms[_mf]))
            print("'%s': [ctx_def([DEFAULT_CONTEXT], '%s')]," % (term, main_form))
            seen.add(term)
    print("Excluded: ", to_str(exclude))
    seen.update(exclude)

    print("=" * 80)
    print("Remaining: %d" % len(set(prefix_terms) - seen))
    for term, full_terms in sorted(prefix_terms.items(), key=lambda _k:'%2d%s' % (len(_k[0]), _k[0])):
        if term in seen:
            continue
        print(u'%s%s => %s' % (term, (u'?' if not is_known_word(term) else ''),
                               ', '.join(u'%s (%s)' % (_t, _t.get_main_form()) for _t in prefix_terms[term])))

    print("Total %d candidates" % len(prefix_terms))
    # print()
    # print("['%s']" % "', '".join(prefix_terms))


def dump_term_dict_from_product_types(config, filename='out/term_dict.dawg'):
    print("Export term dict generated from product type dict")
    term_dict = TypeTermDict()
    TypeTerm.term_dict = term_dict
    print("Load product type dict...")
    from ok.dicts.product_type_dict import reload_product_type_dict
    reload_product_type_dict(config=config, force_text_format=True)
    term_dict.print_stats()
    print("Update dawg...")
    term_dict.update_dawg()
    term_dict.to_file(filename, verbose=True)
    return term_dict


def load_term_dict(filename=None):
    if not filename:
        import ok.dicts
        config = ok.dicts.main_options([])
        filename = config.term_dict
    term_dict = TypeTermDict()
    TypeTerm.term_dict = term_dict
    term_dict.from_file(filename, verbose=True)
    return term_dict


def print_logged_contexts_for_product_type_dict(config):
    print("Print all product types inspired context for ContextDependent terms")
    term_dict = load_term_dict(config.term_dict)
    print("Load product type dict...")
    from ok.dicts.product_type_dict import reload_product_type_dict
    pdt = reload_product_type_dict(config=config)
    print("Update dawg...")
    term_dict.update_dawg()
    print("Run through all types terms main forms")
    ContextDependentTypeTerm._context_log_enabled = True
    for p_type in pdt.get_type_tuples():
        p_type.get_main_form_term_ids()
    print('{')
    for term_id in range(1, term_dict.get_max_id() + 1):
        term = term_dict.get_by_id(term_id)
        if isinstance(term, ContextDependentTypeTerm):
            context_log = term._context_log
            # print('%s => [%s]' % (term, '], ['.join(' + '.join(context) for context in context_log)))
            ctx_terms = sorted(set(tc for context in context_log for tc in context if tc != term))
            print("    '%s': [ctx_definition(['%s'], '%s')]," % (term, "', '".join(ctx_terms), term))
    print('}')


if __name__ == '__main__':
    import sys
    import ok.dicts.term as ot
    config = main_options(sys.argv)
    if config.action == 'dump-pdt':
        ot.dump_term_dict_from_product_types(config)
    elif config.action == 'print-prefixes':
        ot.load_term_dict()
        ot.print_prefix_word_candidates()
    elif config.action == 'print-logged-context':
        ot.print_logged_contexts_for_product_type_dict(config)