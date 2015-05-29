# -*- coding: utf-8 -*-
from collections import defaultdict, namedtuple, OrderedDict
import re
from ok.dicts import get_word_normal_form, cleanup_token_str

TYPE_TERM_PROPOSITION_LIST = (u'в', u'с', u'со', u'из', u'для', u'и', u'на', u'без', u'к', u'не', u'де', u'по')
TYPE_TERM_PROPOSITION_AND_WORD_LIST = (u'со',)


class TypeTerm(unicode):
    # Multi-variant string. It has main representation but also additional variants which can be used for
    # combinations. Typical example is compound words separated by hyphen.

    not_a_term_character_pattern = re.compile(u'[^А-Яа-я0-9A-Za-zёЁ]+', re.U)

    __terms = defaultdict(set)
    """@type: dict of (unicode, int)"""
    __terms_idx = [None] * 10000
    """@type: list[unicode]"""
    __next_idx = 1  # 0 is not used to avoid matching with None

    @staticmethod
    def __term_to_idx(term):
        # Naive non-thread safe realization
        # If int - Tuple unfolding - referenced directly to indexes. Just return it
        if isinstance(term, int):
            idx = term
        elif isinstance(term, TypeTerm):
            idx = TypeTerm.__terms.get(term)
            if idx is None:
                idx = TypeTerm.__next_idx
                TypeTerm.__terms_idx[idx] = term
                TypeTerm.__terms[term] = idx
                TypeTerm.__next_idx += 1
                if TypeTerm.__next_idx == len(TypeTerm.__terms_idx):
                    new_idx = [None] * (int(len(TypeTerm.__terms_idx) * 1.75))
                    new_idx[:len(TypeTerm.__terms_idx)] = TypeTerm.__terms_idx[:]
                    TypeTerm.__terms_idx = new_idx
        else:
            raise Exception("Only TypeTerms or int are accepted but %s is given" % type(term))
        return idx

    __slots__ = ('_term_id', '_variants', '_do_not_pair', '_always_pair', '_word_forms')

    def __new__(cls, *args):
        if args and isinstance(args[0], TypeTerm) and getattr(args[0], '_term_id', None) is not None:
            return args[0]
        self = unicode.__new__(cls, *args)
        """@type: TypeTerm"""
        if not cls.is_valid_term_for_type(self):
            raise Exception("Invalid term for type %s. Use another class or .make() method. Term: %s" % (cls, self))

        exist_term = TypeTerm.get_by_unicode(self)
        if exist_term is not None:
            self = exist_term
        else:
            self._term_id = None
        return self

    def __init__(self, from_str=''):
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

            # Put term to cache and assign id
            self._term_id = TypeTerm.__term_to_idx(self)

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

    @staticmethod
    def is_valid_term_for_type(term_str):
        return TypeTerm.is_a_term(term_str) and not TypeTerm.is_compound_term(term_str)

    @property
    def term_id(self):
        return self._term_id

    @staticmethod
    def get_by_id(term_id):
        """
        @param int term_id: Term ID
        @rtype: TypeTerm|None
        """
        return TypeTerm.__terms_idx[term_id] if term_id < TypeTerm.__next_idx else None

    @staticmethod
    def get_by_unicode(term_str):
        term_id = TypeTerm.__terms.get(term_str)
        return TypeTerm.get_by_id(term_id) if term_id is not None else None

    @staticmethod
    def make(term_str):
        """
        Factory method returns TypeTerm instance of correct type.
        Type is determined by term_str using .is_valid_term_for_type() method of each known type.
        @param unicode term_str: string
        @rtype: TypeTerm
        """
        if isinstance(term_str, TypeTerm) and not term_str.is_new():
            return term_str
        if TagTypeTerm.is_valid_term_for_type(term_str):
            term = TagTypeTerm(term_str)
        elif CompoundTypeTerm.is_valid_term_for_type(term_str):
            try:
                term = WithPropositionTypeTerm(term_str)
            except:
                try:
                    term = AbbreviationTypeTerm(term_str)
                except:
                    term = CompoundTypeTerm(term_str)
        else:
            term = TypeTerm(term_str)
        return term

    def get_main_form(self):
        return self.word_forms[0]
        # return min(self.word_forms, key=TypeTerm.term_id.fget)

    def is_compatible_with(self, another_term):
        if another_term in self._always_pair:
            return True
        # Default logic - do not pair with self, own variants, and own synonyms, except it was declared as always_pair
        if another_term == self or another_term in self.word_forms:
            return False
        # Even if pass default logic - do not pair anyway if declared as do_not_pair
        if another_term in self._do_not_pair:
            return False
        return True

    def always_pair(self, *cp):
        self._always_pair.update(cp)

    def do_not_pair(self, *dnp):
        self._do_not_pair.update(dnp)

    @property
    def word_forms(self):
        """
        Collect and return all known word forms including itself. Main form will be always first (i.e. if term itself
        is not a main form it can be not the first in the list). Word forms are cached once and never changes
        @rtype: list[TypeTerm]
        """
        if self._word_forms is None:
            self._word_forms = self._collect_self_word_forms()

        return self._word_forms[:]

    # TODO: Implement synonyms pre-processing for unfolding of abbreviations to normal forms
    # TODO: Actually this implementation is incorrect because synonyms are context dependent
    syn_set = namedtuple('SynonymsSet', 'main_form options')
    synonyms = [
                syn_set(get_word_normal_form(u'охлажденная'), {u'охл', u'охлажденная'}),
                syn_set(get_word_normal_form(u'сельдь'), {u'сельдь', u'селедка'}),
                syn_set(get_word_normal_form(u'оливковое'), {u'олив', u'оливковое'}),
                syn_set(get_word_normal_form(u'на кости'), {u'н/к', u'на кости'}),
                ]  # First ugly implementation. EXPERIMENTAL!
    synonyms_index = {syn: syn_set_def for syn_set_def in synonyms for syn in syn_set_def.options}
    """@type synonyms_index: dict of (unicode, SynonymsSet)"""

    def _collect_self_word_forms(self):
        """
        @rtype: list[TypeTerm]
        """
        syns = {self}
        main_form_syn = None
        if self in TypeTerm.synonyms_index:
            syn_set_def = TypeTerm.synonyms_index[self]
            syns.update(syn_set_def.options)
            syns.update(map(get_word_normal_form, syn_set_def.options))
            main_form_syn = syn_set_def.main_form

        else:
            # Try to guess about normal form of word and treat it as synonym
            self_normal_form = get_word_normal_form(self, strict=True)
            if self != self_normal_form:
                syns.add(self_normal_form)
                main_form_syn = self_normal_form

        collected_forms = [self.make(main_form_syn)] if main_form_syn else []
        for syn in syns:
            if syn != main_form_syn:
                term = self.make(syn)
                collected_forms.append(term)
        return collected_forms

    @staticmethod
    def print_stats():
        print 'TypeTerm set stats:\r\n\tterms: %d\r\n\tnext term index: %d' %\
              (len(TypeTerm.__terms), TypeTerm.__next_idx)

    @staticmethod
    def parse_term_string(terms_str):
        """
        Parse long string of multiple terms and return list of TypeTerms with respectful types.
        Main processing here is compound terms with proposition detection. Proposition is added to next word(s) as well.
        Also 'and' proposition is processed. All other work is delegated to TypeTerm.make()
        @param unicode terms_str: string of terms
        @rtype: list[TypeTerm]
        """
        words = re.split(u'\s+', cleanup_token_str(terms_str))
        terms = []
        """@type: list[TypeTerm]"""
        buf = u''
        buf_count = 0
        for w in words:
            if w and TypeTerm.is_a_term(w):
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


class CompoundTypeTerm(TypeTerm):
    """
    Term consists of two other simple TypeTerms
    If sub-terms are separated by non-space than space separated variant will be added as variant
    @type _sub_terms: list[TypeTerm]
    """

    @staticmethod
    def is_valid_term_for_type(term_str):
        return TypeTerm.is_a_term(term_str) and TypeTerm.is_compound_term(term_str)

    def _tokenize(self, max_split=0):
        tokens = re.split(TypeTerm.not_a_term_character_pattern, self, maxsplit=max_split)
        return filter(len, tokens)

    def _filter_tokens(self, tokens):
        # This is for override logic of token processing
        return tokens

    def _validate_tokens(self, tokens):
        return tokens and (len(tokens) > 1 or tokens[0] != self)

    def _make_token_terms(self, tokens):
        token_terms = [TypeTerm.make(token) for token in tokens]
        spaced_form = u' '.join(token_terms)
        if self != spaced_form and spaced_form not in token_terms:
            token_terms.append(self.make(spaced_form))
        return token_terms

    def __init__(self, from_str=''):
        # Check that is a new instance creation to avoid re-initialization for cached instances
        if self.is_new():
            tokens = self._tokenize()
            tokens = self._filter_tokens(tokens)
            if not self._validate_tokens(tokens):
                raise Exception(u'This is not a %s: %s' % (type(self), unicode(self)))
            self._sub_terms = self._make_token_terms(tokens)
        super(CompoundTypeTerm, self).__init__(from_str)

    @property
    def sub_terms(self):
        return self._sub_terms[:]

    def is_compatible_with(self, another_term):
        if not super(CompoundTypeTerm, self).is_compatible_with(another_term):
            # Check override rules
            return False
        if any(not sub_term.is_compatible_with(another_term) for sub_term in self._sub_terms):
            return False
        return True

    @property
    def simple_sub_terms(self):
        """
        Return only simple sub terms, i.e. skip white spaces form, proposition form, etc
        Usually it is sequence of original tokens
        """
        return [st for st in self.sub_terms if not isinstance(st, CompoundTypeTerm)]


class WithPropositionTypeTerm(CompoundTypeTerm):
    """
    Special form of compound Term consists of proposition and other TypeTerms
    Proposition is not considered as sub-term when checking compatibility (aka stop-words)
    Proposition is considered as meaningful before terms with length more then two. Other cases should be treated as
    AbbreviationTypeTerm
    @type proposition: unicode
    """
    def __init__(self, from_str=''):
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
            self.proposition = tokens[0]
            tokens.pop(0)
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

    def is_compatible_with(self, another_term):
        if not super(WithPropositionTypeTerm, self).is_compatible_with(another_term):
            return False
        if isinstance(another_term, WithPropositionTypeTerm):
            # Compatible terms cannot start with the same proposition
            if self.proposition == another_term.proposition:
                return False
        return True


class TagTypeTerm(TypeTerm):
    # Special term starting with hash - it is used for unparseable tag names
    @staticmethod
    def is_valid_term_for_type(term_str):
        return TypeTerm.is_a_term(term_str) and term_str.startswith(u'#')


class AbbreviationTypeTerm(CompoundTypeTerm):
    # Short form of compound term consists of abbreviation in one or multiple parts
    # Short sub-terms are not considered as separate terms and treated only as a whole with other sub-terms

    def _make_token_terms(self, tokens):
        sub_terms = super(AbbreviationTypeTerm, self)._make_token_terms(tokens)
        # Filter non simple terms or simple but long, i.e. meaningful
        return [st for st in sub_terms if not TypeTerm.is_valid_term_for_type(st) or len(st) > 2]

    def _validate_tokens(self, tokens):
        comp_valid = super(AbbreviationTypeTerm, self)._validate_tokens(tokens)
        return comp_valid and any(len(t) <= 2 for t in tokens)