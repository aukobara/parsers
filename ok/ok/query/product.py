# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

from ok.dicts.product_type_dict import ProductTypeDict
from ok.dicts.russian import RE_WORD_OR_NUMBER_CHAR_SET
from ok.dicts.term import TermContext, CompoundTypeTerm, ContextRequiredTypeTermException, TypeTerm
from ok.query import tokens
from ok.query.tokens import RE_QUERY_SEPARATOR

"""
Module for query helpers using in product query processing, data extraction, etc.
"""


class ProductQuery(object):
    """
    Build parsing context for given Product. It is assumed that Product is immutable during life of the query.
    Thus, many fields and data are cached.
    """

    ptd = ProductTypeDict()

    def __init__(self, fields=None):
        self._fields = dict(fields or {})
        self._sqn_query = None
        self._context = {}
        self._tail = None

    @classmethod
    def from_product(cls, product):
        assert isinstance(product, dict)
        return cls(product)

    @classmethod
    def from_sqn(cls, sqn, context=None, type_filter=None):
        p_types = cls.ptd.collect_sqn_type_tuples(sqn, context=context)
        if type_filter is not None:
            p_types = type_filter(p_types)
        fields = {'sqn': sqn,
                  'pfqn': sqn,
                  'types': set(p_types)
                  }
        return cls(fields)

    @classmethod
    def from_pfqn(cls, pfqn, context=None, type_filter=None):
        pfqn_tokens = ProductQueryParser(pfqn) if not isinstance(pfqn, ProductQueryParser) else pfqn
        fat = pfqn_tokens.fat()
        pack = pfqn_tokens.pack()
        weight = pfqn_tokens.weight()

        remain = pfqn_tokens.remaining_tokens()

        brand = None
        if remain:
            brand, remain = cls.parse_brand(remain)

        p_types = cls.ptd.collect_sqn_type_tuples(remain, context=context) if remain else set()
        if type_filter is not None and p_types:
            p_types = type_filter(p_types)

        fields = {'pfqn': pfqn,
                  'sqn': remain,
                  'weight': weight,
                  'fat': fat,
                  'pack': pack,
                  'types': set(p_types),
                  'brand': brand,
                  'brand_detected': bool(brand)
                  }
        return cls(fields)

    @classmethod
    def parse_brand(cls, remain):
        from ok.query.find import find_brands

        brand = None
        with find_brands(remain) as brand_rs:
            if brand_rs.size > 0:
                brand = next(brand_rs.data, None)
                if brand:
                    remain = brand_rs.not_matched_tokens()

        return brand, remain

    def sqn_query(self):
        """Return Product's SQN in parsed Query form"""
        sqn_query = self._sqn_query
        if sqn_query is None:
            from ok.query import parse_query

            sqn = self.sqn
            sqn_query = self._sqn_query = parse_query(sqn)
        return sqn_query

    def term_context(self, required=None):
        required = required or ['sqn', 'tags', 'types']
        context_key = frozenset(required)
        context = self._context.get(context_key)
        if context is None:
            fields = self._fields

            context_items = self.sqn_query()[:] if 'sqn' in context_key else []

            if 'tags' in context_key and 'tags' in fields:
                context_items.extend(fields['tags'])

            if 'types' in context_key and 'types' in fields:
                context_items.extend(pt for p_type in fields['types'] for pt in p_type)

            context = self._context[context_key] = TermContext.ensure_context(context_items)
        return context

    @property
    def pfqn(self):
        return self._fields['pfqn']

    @property
    def sqn(self):
        return self._fields['sqn']

    @property
    def brand(self):
        return self._fields['brand']

    @property
    def weight(self):
        return self._fields['weight']

    @property
    def fat(self):
        return self._fields['fat']

    @property
    def pack(self):
        return self._fields['pack']

    @property
    def types(self):
        return frozenset(self._fields['types'])

    @property
    def tags(self):
        return frozenset(self._fields['tags'])

    @property
    def tail(self):
        """
        @return SQN tokens that are not covered by other searchable parts like types, brand, etc.
                It may be useful for better scoring of product with unique terms
        """
        tail = self._tail
        if tail is not None:
            return tail

        sqn_terms = TypeTerm.parse_term_string(self.sqn_query())
        context = self.term_context()

        all_type_terms = set()
        for p_type in self.types:
            all_type_terms.update(wf for t in p_type for wf in t.word_forms(context=context, fail_on_context=False))

        tail = []
        for term in sqn_terms:
            sub_terms = term.simple_sub_terms if isinstance(term, CompoundTypeTerm) else [term]
            for sub_term in sub_terms:
                if sub_term not in tail:

                    for type_term in all_type_terms:
                        if not type_term.is_compatible_with(sub_term, context=context) or \
                           not sub_term.is_compatible_with(type_term, context=context):
                            sub_term_in_types = True
                            break
                    else:
                        sub_term_in_types = False
                    if sub_term_in_types:
                        continue

                    # No one word form of term is in type terms
                    tail.append(sub_term)
                    try:
                        sub_term_main_form = sub_term.get_main_form(context=context)
                        if sub_term != sub_term_main_form and sub_term_main_form not in tail:
                            tail.append(sub_term_main_form)
                    except ContextRequiredTypeTermException:
                        # Cannot recognize term in this context. Ignore main form
                        pass

        self._tail = tail
        return tail[:]

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

RE_NUMBER_FLOAT = '\d+(?:[.,]\d+)?'

RE_WEIGHT_MULTIPLIER_NUMBER = '\d+\s*(?:шт|пак)?'
RE_WEIGHT_MULTIPLIER_SEP = '(?:х|\*|x|/)'
RE_TEMPLATE_PFQN_WEIGHT_SHORT = '(?:кг|г|л|мл|гр)\.?'
RE_TEMPLATE_PFQN_WEIGHT_FULL = ('(?:фас(?:\.|овка)?\s*)?'
                                '(?:{NUMBER}\s*{SEP}\s*)?'
                                '{FLOAT}\s*{SHORT}'
                                '(?:{SEP}{NUMBER})?').format(SHORT=RE_TEMPLATE_PFQN_WEIGHT_SHORT, FLOAT=RE_NUMBER_FLOAT,
                                                             NUMBER=RE_WEIGHT_MULTIPLIER_NUMBER, SEP=RE_WEIGHT_MULTIPLIER_SEP)

RE_TEMPLATE_PFQN_FAT_MDZH = ('(?:(?:с\s)?м\.?д\.?ж\.? в сух(?:ом)?\.?\s?вещ(?:-|ест)ве'
                             '|массовая доля жира в сухом веществе)')
RE_TEMPLATE_PFQN_FAT = ('(?:{MDZH}\s*)?(?:{FLOAT}%?\s*-\s*)?{FLOAT}\s*%(?:\s*ж(?:\.|ирн(?:\.|ости)?)?)?'
                        '(?:\s*{MDZH})?').format(MDZH=RE_TEMPLATE_PFQN_FAT_MDZH, FLOAT=RE_NUMBER_FLOAT)

RE_TEMPLATE_PFQN_PACK = 'т/пак|ж/б|ст/б|м/у|с/б|ст\\\б|ст/бан|ст/бут|бут|пл/б|пл/бут|пэтбутылка|пл(?:\.|$)|(?:пл.?)?кор|коробка|в\sп/к|к(?:арт)?/пач(?:ка)?' + \
                        '|(?:\d+\s*)пак|\d+\s*таб|\d+\s*саше|(?:\d+\s*)?пир(?:ам(?:идок)?)?' + \
                        '|(?:\d+\s*)?шт|ф/уп|в/у|п/э|жесть|круг|обрам' + \
                        '|вакуум|нарезка|нар|кв стакан|стакан|ванночка|в\sванночке|дой[-/ ]?пак|пюр[-/ ]?пак' + \
                        '|зип(?:\-пак(?:ет)?)?|д/пак|(?:п/|пл.)?пак(?:ет)?|(?:пл.)?уп(?:ак(?:овка)?)?|пэт|туба|(?:пл.)?ведро|бан|лоток|фольга' + \
                        '|фас(?:ованные)?|н/подл|ф/пакет|0[.,]5|0[.,]75|0[.,]33|0[.,]57'

RE_TEMPLATE_NON_WORD = '[^%s\-]' % RE_WORD_OR_NUMBER_CHAR_SET
RE_TEMPLATE_SEPARATOR = '[%s]' % RE_QUERY_SEPARATOR


class ProductQueryParser(tokens.Query):

    class WeightFullQueryToken(tokens.QueryToken):
        regex = RE_TEMPLATE_PFQN_WEIGHT_FULL
        group_name = 'weightfull'
        pre_condition = '\D'
        post_condition = RE_TEMPLATE_NON_WORD

    class WeightShortQueryToken(tokens.QueryToken):
        regex = RE_TEMPLATE_PFQN_WEIGHT_SHORT
        group_name = 'weightshort'
        pre_condition = RE_TEMPLATE_SEPARATOR
        post_condition = RE_TEMPLATE_SEPARATOR

    class FatQueryToken(tokens.QueryToken):
        regex = RE_TEMPLATE_PFQN_FAT
        group_name = 'fat'

    class PackQueryToken(tokens.QueryToken):
        regex = RE_TEMPLATE_PFQN_PACK
        group_name = 'pack'
        pre_condition = RE_TEMPLATE_NON_WORD
        post_condition = RE_TEMPLATE_NON_WORD

    token_reg = [WeightFullQueryToken, WeightShortQueryToken, FatQueryToken, PackQueryToken] + tokens.DefaultQuery.token_reg

    def weight(self):
        weight_tokens = self.items_of_type(ProductQueryParser.WeightFullQueryToken) or self.items_of_type(ProductQueryParser.WeightShortQueryToken)
        return ' + '.join(weight_tokens) if weight_tokens else None

    def fat(self):
        fat_tokens = self.items_of_type(ProductQueryParser.FatQueryToken)
        return ' + '.join(fat_tokens) if fat_tokens else None

    def pack(self):
        pack_tokens = self.items_of_type(ProductQueryParser.PackQueryToken)
        return ' + '.join(pack_tokens) if pack_tokens else None

    def remaining_tokens(self):
        """@rtype: list[ok.query.tokens.QueryToken]"""
        return self.words
