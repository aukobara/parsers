# -*- coding: utf-8 -*-
from collections import defaultdict, namedtuple, OrderedDict
import re
import dawg
import itertools

from ok.dicts import cleanup_token_str
from ok.dicts.russian import get_word_normal_form, is_known_word

TYPE_TERM_PROPOSITION_LIST = (u'в', u'с', u'со', u'из', u'для', u'и', u'на', u'без', u'к', u'не', u'де', u'по', u'под')
TYPE_TERM_PROPOSITION_AND_WORD_LIST = (u'со',)


class TypeTermException(Exception):
    pass

class ContextRequiredTypeTermException(TypeTermException):
    pass


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
        dawg_id_list = self.__terms_dawg.get(term_str)
        term_id = self.__terms.get(term_str) if not dawg_id_list else int(dawg_id_list[0])
        return term_id

    def clear(self):
        self.__terms = defaultdict(set)
        self.__terms_dawg = dawg.BytesDAWG()
        self.__terms_idx = [None] * 10000
        self.__next_idx = 1

    def update_dawg(self):
        # Convert __terms dict to DAWG and clear. Search by prefixes can be used in DAWG only.
        # All new terms will be saved in __terms only and not searchable by prefixes until next update_dawg()
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
                    count_wf += len(term.word_forms())
                seen_set.add(term_str)
            key_set = set(self.__terms.keys())
        new_dawg = dawg.BytesDAWG((unicode(k), bytes(v)) for k, v in
                                  itertools.chain(self.__terms_dawg.iteritems(), self.__terms.iteritems()))
        assert len(new_dawg.keys()) == len(self.__terms.keys()) + len(self.__terms_dawg.keys()), \
            "DAWG does not match to terms dict!"
        self.__terms_dawg = new_dawg
        self.__terms.clear()

        # TODO: invalidate PrefixTypeTerms, i.e. check they are still valid PrefixTypeTerm.
        # To pass full check they have to be recreated and converted to simple type if required
        assert not any(isinstance(self.get_by_unicode(key), PrefixTypeTerm) for key in self.__terms_dawg.keys()), \
            "TODO: INVALIDATE Prefix Types before merge them to DAWG"

    def save_term(self, term):
        return self.__term_to_idx(term)

    def get_by_id(self, term_id):
        """
        @param int term_id: Term ID
        @rtype: TypeTerm|None
        """
        return self.__terms_idx[term_id] if term_id < self.__next_idx else None

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
        keys = self.__terms_dawg.keys(unicode(prefix))
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
        key = unicode(prefix)
        prefixed_keys = self.__terms_dawg.keys(key)
        if not_compound:
            prefixed_keys = [k for k in prefixed_keys if not CompoundTypeTerm.is_valid_term_for_type(k)]
        return len(prefixed_keys) - (1 if not count_self and key in self.__terms_dawg else 0)

    def print_stats(self):
        print 'TypeTerm set stats:\r\n\tterms: %d\r\n\tterms(dawg): %d\r\n\tnext term index: %d' %\
              (len(self.__terms), len(self.__terms_dawg.keys()), self.__next_idx)

    def to_file(self, filename, verbose=False):
        if verbose:
            print "Save current term_dict dawg to file: %s" % filename
            if self.__terms:
                print "WARN: Non-dawg dict is NOT empty and will not be saved! Update DAWG first!"
        if self.__terms_dawg:
            self.__terms_dawg.save(filename)
        if verbose:
            print "Dumped %d terms to %s" % (len(self.__terms_dawg.keys()), filename)

    def from_file(self, filename, verbose=False):
        if verbose:
            print "Load term_dict dawg from file: %s" % filename
            if self.__terms:
                print "WARN: Non-dawg dict is NOT empty and will be lost!"
        self.clear()
        new_dawg = dawg.BytesDAWG()
        new_dawg.load(filename)
        term_id = 0
        for term_str, term_id in sorted(new_dawg.iteritems(), key=lambda _t: int(_t[1])):
            term_id = int(term_id)
            term = TypeTerm.make(term_str)
            assert term.term_id == term_id
        assert self.__next_idx == term_id + 1, "Internal index does not match to dawg data!"
        self.update_dawg()
        assert list(new_dawg.keys()) == list(self.__terms_dawg.keys())
        if verbose:
            print "Loaded %d terms from %s" % (len(self.__terms_dawg.keys()), filename)


class TypeTerm(unicode):
    # Multi-variant string. It has main representation but also additional variants which can be used for
    # combinations. Typical example is compound words separated by hyphen.

    not_a_term_character_pattern = re.compile(u'[^А-Яа-я0-9A-Za-zёЁ]+', re.U)

    __slots__ = ('_term_id', '_variants', '_do_not_pair', '_always_pair', '_word_forms')

    term_dict = TypeTermDict()

    def __new__(cls, *args):
        if args and isinstance(args[0], TypeTerm) and getattr(args[0], '_term_id', None) is not None:
            return args[0]
        self = unicode.__new__(cls, *args)
        """@type: TypeTerm"""
        if not cls.is_valid_term_for_type(self):
            raise TypeTermException(u"Invalid term for type %s. Use another class or .make() method. Term: %s" %
                                    (cls, unicode(self)))

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
        @param unicode|TypeTerm term_str: string
        @rtype: TypeTerm
        """
        if isinstance(term_str, TypeTerm) and not term_str.is_new():
            return term_str
        term = None
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
        @param list[TypeTerm]|tuple[TypeTerm]|None context: list of other terms are met in the same context as this
        @rtype: TypeTerm
        @return: term with Main Form of this. It may be the same term if it is own main form.
        @raise ContextRequiredTypeTermException: if context is required to recognize Main Form and specified context is
                empty or not enough
        """
        return self.word_forms()[0]
        # return min(self.word_forms, key=TypeTerm.term_id.fget)

    def is_compatible_with(self, another_term, context=None):
        if another_term in self._always_pair:
            return True
        # Default logic - do not pair with self, own variants, and own synonyms, except it was declared as always_pair
        if another_term == self or another_term in self.word_forms(context):
            return False
        # Even if pass default logic - do not pair anyway if declared as do_not_pair
        if another_term in self._do_not_pair:
            return False
        return True

    def always_pair(self, *cp):
        self._always_pair.update(cp)

    def do_not_pair(self, *dnp):
        self._do_not_pair.update(dnp)

    def word_forms(self, context=None, fail_on_context=False):
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
    __synonyms_index = None
    syn_set = namedtuple('SynonymsSet', 'main_form options')

    @staticmethod
    def get_synonyms_index():
        """
        @rtype dict of (unicode, SynonymsSet)
        """
        if TypeTerm.__synonyms_index is None:
            synonyms = [
                TypeTerm.syn_set(get_word_normal_form(u'охлажденная'), {u'охл', u'охлажденная'}),
                TypeTerm.syn_set(get_word_normal_form(u'оливковое'), {u'олив', u'оливковое'}),
                TypeTerm.syn_set(get_word_normal_form(u'на кости'), {u'н/к', u'на кости'}),
                ]  # First ugly implementation. EXPERIMENTAL!
            TypeTerm.__synonyms_index = {syn: syn_set_def for syn_set_def in synonyms for syn in syn_set_def.options}
        return TypeTerm.__synonyms_index

    def _collect_self_word_forms(self):
        """
        @rtype: list[TypeTerm]
        """
        syns = {self}
        main_form_syn = None
        if self in self.get_synonyms_index():
            syn_set_def = self.get_synonyms_index()[self]
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

    def as_string(self):
        return unicode(self)


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
        tokens = re.split(TypeTerm.not_a_term_character_pattern, self, maxsplit=max_split)
        return filter(len, tokens)

    def _filter_tokens(self, tokens):
        # This is for override logic of token processing
        return tokens

    def _validate_tokens(self, tokens):
        return tokens and (len(tokens) > 1 or tokens[0] != self)

    def _make_token_terms(self, tokens):
        token_terms = [TypeTerm.make(token) for token in tokens]
        self._spaced_form = u' '.join(token_terms)
        if self != self._spaced_form and self._spaced_form not in token_terms:
            token_terms.append(self.make(self._spaced_form))
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
                raise TypeTermException(u'This is not a %s: %s' % (type(self), unicode(self)))
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

    """
    def _collect_self_word_forms(self):
        # If CompoundTypeTerm has spaced form different than itself it must go first as Main Form to match other
        # compound terms with different delimiters
        collected_forms = super(CompoundTypeTerm, self)._collect_self_word_forms()
        if self._spaced_form != self:
            main_form = TypeTerm.make(self._spaced_form).get_main_form()
            if not collected_forms or main_form != collected_forms[0]:
                collected_forms = [main_form] + collected_forms
        return collected_forms
    """


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

    def is_compatible_with(self, another_term, context=None):
        if not super(WithPropositionTypeTerm, self).is_compatible_with(another_term):
            return False
        if isinstance(another_term, WithPropositionTypeTerm):
            # Compatible terms cannot start with the same proposition
            if self.proposition == another_term.proposition:
                return False
        return True

    def _collect_self_word_forms(self):
        # For proposition it is clear which sub-term represent Main Form - it has only one real sub-term
        collected_forms = super(WithPropositionTypeTerm, self)._collect_self_word_forms()
        main_form = self.sub_terms[0].get_main_form()
        if not collected_forms or main_form != collected_forms[0]:
            collected_forms = [main_form] + collected_forms
        return collected_forms


class TagTypeTerm(TypeTerm):
    # Special term starting with hash - it is used for unparseable tag names
    @classmethod
    def is_valid_term_for_type(cls, term_str):
        return cls.is_a_term(term_str) and term_str.startswith(u'#')

    def as_string(self):
        return unicode(self.replace(u'#', ''))


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

    def _collect_self_word_forms(self):
        # For abbreviation - special case exist when it is clear which sub-term represent Main Form -
        # when one only sub-term is long and can represent normal term.
        collected_forms = super(AbbreviationTypeTerm, self)._collect_self_word_forms()
        if len(self.simple_sub_terms) == 1:
            main_form = self.simple_sub_terms[0].get_main_form()
            if not collected_forms or main_form != collected_forms[0]:
                collected_forms = [main_form] + collected_forms
        return collected_forms


class PrefixTypeTerm(TypeTerm):
    # Short word that has more longer unique form

    @classmethod
    def is_valid_term_for_type(cls, term_str):
        simple_type_valid = super(PrefixTypeTerm, cls).is_valid_term_for_type(term_str)
        if not simple_type_valid or len(term_str) <= 3:
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
                raise TypeTermException(u'This is not a %s: %s' % (type(self), unicode(self)))
            self._prefixed_terms = prefixed_terms
        super(PrefixTypeTerm, self).__init__(from_str)

    def _collect_self_word_forms(self):
        collected_forms = super(PrefixTypeTerm, self)._collect_self_word_forms()
        main_form_term = self._prefixed_terms[0].get_main_form()
        collected_forms.extend(self._prefixed_terms)

        if main_form_term and (not collected_forms or collected_forms[0] != main_form_term):
            collected_forms = [main_form_term] + collected_forms

        return collected_forms


class ContextDependentTypeTerm(TypeTerm):

    DEFAULT_CONTEXT = u'__default__'
    ctx_definition = namedtuple('_ctx_definition', 'ctx_terms main_form')
    # If any term in context of ctx_terms use main_form
    ctx_dependent_terms = {u'мар': [ctx_definition([u'йогурт'], u'маракуйя')]}

    @classmethod
    def is_valid_term_for_type(cls, term_str):
        simple_valid = super(ContextDependentTypeTerm, cls).is_valid_term_for_type(term_str)
        return simple_valid and term_str in cls.ctx_dependent_terms

    def __init__(self, from_str=''):
        """@param unicode from_str: term string"""
        if self.is_new():
            self.ctx_map = {}
            """@type: dict of (TypeTerm, TypeTerm)"""
            for ctx_def in self.ctx_dependent_terms[self]:
                for ctx_term_str in ctx_def.ctx_terms:
                    ctx_term = TypeTerm.make(ctx_term_str)
                    main_form_term = TypeTerm.make(ctx_def.main_form)
                    if isinstance(ctx_term, ContextDependentTypeTerm) or \
                            isinstance(main_form_term, ContextDependentTypeTerm):
                        raise TypeTermException(
                            "ContextDependent term's [%s] context cannot be defined using another "
                            "ContextDependent term: %s" %
                            (self, ctx_term))
                    self.ctx_map[ctx_term.get_main_form(context=None)] = main_form_term
        super(ContextDependentTypeTerm, self).__init__(from_str)

    def get_main_form(self, context=None):
        """
        @param list[TypeTerm]|None context: list of other terms are met in the same context as this
        @rtype: TypeTerm
        """
        main_form = None
        """@type: TypeTerm|None"""
        if context:
            ctx_term_match = None
            for ctx_term in context:
                if ctx_term == self:
                    continue
                if main_form is None:
                    main_form = self.ctx_map.get(ctx_term.get_main_form(context))
                    ctx_term_match = ctx_term
                else:
                    another_variant = self.ctx_map.get(ctx_term.get_main_form(context))
                    if another_variant and another_variant != main_form:
                        raise ContextRequiredTypeTermException(
                            'Context is too ambiguous: many variants for one term detected: '
                            '%s: 1) %s => %s; 2) %s => %s' %
                            (self, ctx_term_match, main_form, ctx_term, another_variant))
        if not main_form:
            # Check if term accept default context
            main_form = self.ctx_map.get(self.DEFAULT_CONTEXT)
        if not main_form:
            raise ContextRequiredTypeTermException(u'Cannot find definition for context dependent term "%s". '
                                                   u'Context: %s' %
                                                   (self, u' + '.join(context if context else [u'<empty>'])))
        return TypeTerm.make(main_form)

    def word_forms(self, context=None, fail_on_context=True):
        collected_forms = []
        try:
            collected_forms = self.get_main_form(context).word_forms(context) + [self]
        except ContextRequiredTypeTermException:
            if fail_on_context:
                raise
        return collected_forms

    def all_context_word_forms(self):
        collected_word_forms = {self}
        [collected_word_forms.update(main_form.word_forms(context=None)) for main_form in self.ctx_map.values()]
        return list(collected_word_forms)

    def all_context_main_forms(self):
        collected_main_forms = set()
        [collected_main_forms.add(main_form.get_main_form(context=None)) for main_form in self.ctx_map.values()]
        return list(collected_main_forms)

def print_prefix_word_candidates():
    wc = 0
    term_dict = TypeTerm.term_dict
    for i in xrange(1, term_dict.get_max_id() + 1):
        term = term_dict.get_by_id(i)
        if len(term) < 2:
            continue
        full_terms = term_dict.find_by_unicode_prefix(term, return_self=False)
        if full_terms and not any(term in _t.word_forms() or term.get_main_form() in _t.word_forms() for _t in full_terms):
            if len(full_terms) == 1 or \
                    any(_t.get_main_form() != full_terms[0].get_main_form() for _t in full_terms[1:]):
                wc += 1
                print u'%s%s => %s' % (term, (u'?' if not is_known_word(term) else ''),
                                       ', '.join(u'%s (%s)' % (_t, _t.get_main_form())
                                                 for _t in full_terms if term not in _t.word_forms()))
    print "Total %d candidates" % wc


def dump_term_dict_from_product_types(filename):
    print "Export term dict generated from product type dict"
    term_dict = TypeTermDict()
    TypeTerm.term_dict = term_dict
    print "Load product type dict..."
    from ok.dicts.product_type_dict import reload_product_type_dict
    reload_product_type_dict()
    term_dict.print_stats()
    print "Update dawg..."
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
