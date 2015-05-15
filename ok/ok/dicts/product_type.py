# -*- coding: utf-8 -*-
from collections import OrderedDict
from itertools import combinations
import re
import Levenshtein

from ok.dicts.product import Product

TYPE_TUPLE_PROPOSITION_LIST = (u'в', u'с', u'со', u'из', u'для', u'и', u'на', u'без', u'к', u'не', u'де')

TYPE_TUPLE_RELATION_EQUALS = u"equals"
TYPE_TUPLE_RELATION_SIMILAR = u"similar"
TYPE_TUPLE_RELATION_CONTAINS = u"contains"
TYPE_TUPLE_RELATION_SUBSET_OF = u"subset_of"
TYPE_TUPLE_MIN_CAPACITY = 4  # Number of SQNs covered by word combination


class ProductType(tuple):

    class Relation(tuple):

        @staticmethod
        def __new__(cls, *args, **kwargs):
            (from_type, to_type, rel_type) = args
            is_soft = kwargs.get("is_soft", False)
            return tuple.__new__(cls, (from_type, to_type, rel_type, is_soft))

        @property
        def from_type(self): return self[0]
        @property
        def to_type(self): return self[1]
        @property
        def rel_type(self): return self[2]
        @property
        def is_soft(self): return self[3]

        def __unicode__(self):
            return u'%s%s %s' % (self.rel_type, u'~' if self.is_soft else '', self.to_type)

        def __str__(self):
            return self.__unicode__().encode("utf-8")

    def __new__(cls, *args, **kwargs):
        self = tuple.__new__(cls, args)
        self._relations = dict()
        """ @type: dict of (ProductType, ProductType.Relation) """
        return self

    def make_relation(self, p_type2, rel_from, rel_to, is_soft=False):
        """
        Add relation to both self and specified ProductType
        @param ProductType p_type2: another type
        @param ProductType.Relation rel_from: from self to second
        @param ProductType.Relation rel_from: from second to first
        @param bool is_soft: relation will not conflict ever - just for mark, not constraint.
                        It is always can be overwritten by hard relation. But soft relation will never overwrite hard
        @return:
        """
        relation = self._relations.get(p_type2)
        if relation and relation.rel_type != rel_from and not(relation.is_soft or is_soft) :
            raise Exception(u"ProductType%s has conflicting relations already with %s" % (self, p_type2))
        if not relation or (relation.is_soft and not is_soft):
            relation = self.Relation(self, p_type2, rel_from, is_soft=is_soft)
            self._relations[p_type2] = relation
            p_type2.make_relation(self, rel_to, rel_from, is_soft=is_soft)  # Notify second party about relation
        return relation

    def equals_to(self, p_type2):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_EQUALS, TYPE_TUPLE_RELATION_EQUALS)

    def similar(self, p_type2):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_SIMILAR, TYPE_TUPLE_RELATION_SIMILAR, is_soft=True)

    def contains(self, p_type2):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_CONTAINS, TYPE_TUPLE_RELATION_SUBSET_OF)

    def subset_of(self, p_type2):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_SUBSET_OF, TYPE_TUPLE_RELATION_CONTAINS)

    def not_related(self, p_type2):
        relation = self._relations.get(p_type2)
        if relation:
            del self._relations[p_type2]
            p_type2.not_related(self)

    def get_relation(self, r_type2):
        return self._relations.get(r_type2)

    def relations(self, *rel_type):
        """
        @param list[unicode] rel_type: Relation type list. If empty - all return
        @rtype: list[ProductType.Relation]
        """
        return sorted([rel for rel in self._relations.values() if not rel_type or rel.rel_type in rel_type], key=lambda _r: _r.rel_type)

    def related_types(self, *rel_type):
        """
        @param list[unicode] rel_type: Relation type list. If empty - all return
        @rtype: list[ProductType]
        """
        return [rel.to_type for rel in self.relations(*rel_type)]

    def brake_relations(self):
        copy_relations = self._relations.keys()[:]
        self._relations.clear()
        for r_type2 in copy_relations:
            r_type2.not_related(self)

    def __unicode__(self):
        return u' + '.join(self)

    def __str__(self):
        return self.__unicode__().encode("utf-8")


class ProductTypeDict(object):
    """
    @type _root_types: list[ProductType]
    @type _type_tuples: dict of (ProductType, list[unicode])
    """

    VERBOSE = False

    def __init__(self):
        self._root_types = None
        self._type_tuples = None

    @staticmethod
    def collect_sqn_type_tuples(sqn):
        """
        Return dict with tuples for combinations of tokens in each parsed sqn. Source sqn will be as value.
        Join propositions to next word to treat them as single token
        If multiple parsed products with identical sqns are present all them will be in the value list as duplicates.
        It is required to estimate "capacity" of tuple
        @rtype: dict of (ProductType, unicode)
        """
        # TODO: Implement synonyms pre-processing for unfolding of abbreviations to normal forms
        result = dict()

        words = re.split(u'\s+', sqn)
        words1 = []
        buf = u''
        buf_count = 0
        for w in words:
            if w:
                if w in TYPE_TUPLE_PROPOSITION_LIST:
                    buf = w  # join proposition to the next word
                    continue
                if buf:
                    # Add both word variants with proposition and w/o.
                    # TODO: generate proposition forms also for 2-3 next words, not only immediate
                    words1.append(buf + u' ' + w)
                    buf_count += 1
                    if buf_count == 2:
                        buf = u''
                        buf_count = 0
                    # Proposition is added itself as well
                    # words1.append(buf)
                words1.append(w)
        if buf and buf_count == 0: words1.append(buf)

        words1 = list(OrderedDict.fromkeys(words1))
        def is_proposition_form(w1, w2):
            return w2.endswith(u' ' + w1) or w1.endswith(u' ' + w2)
        first_word = words1.pop(0)
        result[ProductType(first_word)] = sqn
        if words1:
            for w in words1:
                result[ProductType(first_word, w)] = sqn
            for w1, w2 in combinations(words1, 2):
                if is_proposition_form(w1, w2):
                    # Do not join same world and form with proposition
                    continue
                result[ProductType(first_word, w1, w2)] = sqn

        # Experimental algorithm when first_word is not considered as very special
        # for w in words1:
        #     result[ProductType(w)] = sqn
        # for w1, w2 in permutations(words1, 2):
        #     if is_proposition_form(w1, w2):
        #         continue
        #     result[ProductType(w1, w2)] = sqn
        # for w1, w2, w3 in permutations(words1, 3):
        #     if is_proposition_form(w1, w2) or is_proposition_form(w2, w3) or is_proposition_form(w1, w3):
        #         continue
        #     result[ProductType(w1, w2, w3)] = sqn
        return result

    @staticmethod
    def collect_type_tuples(products):
        """
        Collect product type tuples for all parsed products using @collect_sqn_type_tuples
        @param collections.Iterable[Product] products: sequence of Products
        @rtype: dict of (ProductType, list[unicode])
        """
        result = dict()
        for product in products:
            product_tuples = ProductTypeDict.collect_sqn_type_tuples(product.sqn)
            for type_tuple, sqn in product_tuples.iteritems():
                existing_sqns = result.get(type_tuple, [])
                existing_sqns.append(sqn)
                result[type_tuple] = existing_sqns
        return result

    @staticmethod
    def update_type_tuples_relationship(type_tuples, verbose=False, cleanup_prev_relations=True):
        """
        Calculate all non-repeatable combinations of type tuples with capacity not less than MIN_TUPLE_CAPACITY
        and check if one tuple is equals or contains (in terms of sqn set) another.
        @param dict of (ProductType, list[unicode]) type_tuples: from collect_type_tuples()
        @param bool verbose: type progress if specified - useful for testing of low capacity huge combinations
        """

        if cleanup_prev_relations:
            for t in type_tuples:
                t.brake_relations()

        i_count = 0
        filtered_type_tuples = [it for it in type_tuples.iteritems() if len(it[1]) >= TYPE_TUPLE_MIN_CAPACITY]
        for t1, t2 in combinations(filtered_type_tuples, 2):
            s1 = set(t1[1])
            s2 = set(t2[1])
            type1 = t1[0]
            """@type: ProductType"""
            type2 = t2[0]
            """@type: ProductType"""

            if s1.issubset(s2):
                if len(s1) < len(s2):
                    type1.subset_of(type2)
                else:
                    type1.equals_to(type2)
            elif s2.issubset(s1):
                type1.contains(type2)

            if len(type1) == len(type2) and not type1.get_relation(type2):
                if Levenshtein.setratio(type1, type2) >= 0.85:
                    # Is it smart??
                    type1.similar(type2)

            i_count += 1
            if verbose and i_count % 10000 == 0: print u'.',
            if verbose and i_count % 1000000 == 0: print i_count
        if verbose: print
        pass

    def build_from_products(self, products):
        """
        Build types graph from sequence of products
        @param collections.Iterable[Product] products: seq of Product
        """
        type_tuples = self.collect_type_tuples(products)
        self.update_type_tuples_relationship(type_tuples, self.VERBOSE)
        self._type_tuples = type_tuples

    def get_type_tuples(self):
        """
        @return dict of ProductTypes
        @rtype: dict of (ProductType, list[unicode])
        """
        if not self._type_tuples:
            raise Exception("You have to build dict first!")

        return dict(self._type_tuples)

    def get_root_type_tuples(self):
        if not self._root_types:
            type_tuples = self.get_type_tuples()
            root_types = []
            for t in type_tuples:
                if not t.relations(TYPE_TUPLE_RELATION_SUBSET_OF):
                    # Type tuple has no structured relations
                    root_types.append(t)
            self._root_types = root_types

        return self._root_types[:]
