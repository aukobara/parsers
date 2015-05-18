# -*- coding: utf-8 -*-
from collections import OrderedDict, namedtuple
from itertools import combinations, product, permutations, chain
import json
import re
import Levenshtein
import sys

from ok.dicts import main_options
from ok.dicts.product import Product

TYPE_TUPLE_PROPOSITION_LIST = (u'в', u'с', u'со', u'из', u'для', u'и', u'на', u'без', u'к', u'не', u'де', u'по')

TYPE_TUPLE_RELATION_EQUALS = u"equals"
TYPE_TUPLE_RELATION_SIMILAR = u"similar"
TYPE_TUPLE_RELATION_ALMOST = u"almost"
TYPE_TUPLE_RELATION_CONTAINS = u"contains"
TYPE_TUPLE_RELATION_SUBSET_OF = u"subset_of"
TYPE_TUPLE_MIN_CAPACITY = 4  # Number of SQNs covered by word combination


class ProductType(tuple):

    class Relation(namedtuple('Relation', 'from_type to_type rel_type is_soft rel_attr')):

        __slots__ = ()

        def __unicode__(self):
            return u'%s%s%s %s' % (self.rel_type, u'[%s]' % unicode(self.rel_attr) if self.rel_attr else '', u'~' if self.is_soft else '', self.to_type)

        def __str__(self):
            return self.__unicode__().encode("utf-8")

    __slot__ = ('_relations',)

    # ProductType instances acts as singleton. All instances are kept here
    __v = set()
    """@type: set[ProductType]"""

    def __new__(cls, *args, **kwargs):
        self = tuple.__new__(cls, args)
        """ @type: dict of (ProductType, ProductType.Relation) """
        self._relations = dict()
        wrapper = EqWrapper(self)
        if wrapper in cls.__v:
            self = wrapper.match
        else:
            cls.__v.add(self)

        return self

    def make_relation(self, p_type2, rel_from, rel_to, is_soft=False, rel_attr_from=None, rel_attr_to=None):
        """
        Add relation to both self and specified ProductType
        @param ProductType p_type2: another type
        @param ProductType.Relation rel_from: from self to second
        @param ProductType.Relation rel_from: from second to first
        @param bool is_soft: relation will not conflict ever - just for mark, not constraint.
                        It is always can be overwritten by hard relation. But soft relation will never overwrite hard
        @param unicode rel_attr_from: Relation may have own attribute (like weight). None, by default
        @return:
        """
        relation = self._relations.get(p_type2)
        if relation and relation.rel_type != rel_from and not(relation.is_soft or is_soft) :
            raise Exception(u"ProductType%s has conflicting relations already with %s" % (self, p_type2))
        if not relation or (relation.is_soft and not is_soft):
            relation = self.Relation(self, p_type2, rel_from, is_soft=is_soft, rel_attr=rel_attr_from)
            self._relations[p_type2] = relation
            # Notify second party about relation
            p_type2.make_relation(self, rel_to, rel_from, is_soft=is_soft,
                                  rel_attr_from=rel_attr_to, rel_attr_to=rel_attr_from)
        return relation

    def equals_to(self, p_type2):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_EQUALS, TYPE_TUPLE_RELATION_EQUALS)

    def similar(self, p_type2, similarity):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_SIMILAR, TYPE_TUPLE_RELATION_SIMILAR, is_soft=True,
                                  rel_attr_from=similarity, rel_attr_to=similarity)

    def almost(self, p_type2, similarity_from, similarity_to):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_ALMOST, TYPE_TUPLE_RELATION_ALMOST, is_soft=True,
                                  rel_attr_from=similarity_from, rel_attr_to=similarity_to)

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


class EqWrapper(ProductType):
    def __new__(cls, *args):
        self = tuple.__new__(cls, args[0])
        self.obj = args[0]
        self.match = None
        return self

    def __eq__(self, other):
        result = (self.obj == other)
        if result:
            self.match = other
        return result

    def __getattr__(self, item):
        return getattr(self.obj, item)


class ProductTypeDict(object):
    """
    @type _root_types: list[ProductType]
    @type _type_tuples: dict of (ProductType, list[unicode])
    """

    # Build type tuples operation may be long. This may help to check progress
    VERBOSE = False

    def __init__(self):
        # ProductTypes are not contained in other types. These are actual roots of classified types
        # as well as remaining unclassified types with unknown relations
        # It is lazily built and have to be drop if type tuples are changed
        self._root_types = None

        # Dict of all ProductTypes mapped to list of SQNs produced them. It is built from Products SQNs or pre-loaded
        # from external source (like file)
        self._type_tuples = None

    class MultiWord(unicode):
        # Multi-variant string. It has main representation but also additional variants which can be used for
        # combinations. Typical example is compound words separated by hyphen.
        _variants = None
        @property
        def variants(self):
            self._variants = self._variants or []
            return self._variants

        @variants.setter
        def variants(self, v):
            self._variants = v

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
                    words1.append(buf + u' ' + w)
                    buf_count += 1
                    if buf_count == 2:
                        buf = u''
                        buf_count = 0
                    # Proposition is added itself as well
                    # words1.append(buf)
                if u'-' in w:
                    # Now it is important the order of words they are added to list. First word is most important in
                    # type detection. Thus, compound words must present meaningful part first
                    # TODO: implement compound terms (~) that can be compared separately but in result are always together
                    multi_w = ProductTypeDict.MultiWord(w)
                    multi_w.variants += w.split(u'-')
                    w = multi_w
                words1.append(w)
        if buf and buf_count == 0: words1.append(buf)

        words1 = list(OrderedDict.fromkeys(words1))
        def is_proposition_form(w1, w2):
            return w2.endswith(u' ' + w1) or w1.endswith(u' ' + w2) or\
                   w2.startswith(w1 + u' ') or w1.startswith(w2 + u' ') or\
                    w2.endswith(u'-' + w1) or w1.endswith(u'-' + w2) or\
                    w2.startswith(w1 + u'-') or w1.startswith(w2 + u'-')

        first_word = words1.pop(0)
        def add_combinations(_words, n):
            vf = [[]]
            vf[0] = [first_word] + (first_word.variants if isinstance(first_word, ProductTypeDict.MultiWord) else [])
            if len(vf[0]) > 1:
                # For MultiWord add optional combinations with itself
                vf.append(vf[0] + [u''])
            for wvf in product(*vf):
                for _w in combinations(_words, n):
                    v = [[]] * len(_w)
                    for i, _wi in enumerate(_w):
                        v[i] = [_w[i]] + (_w[i].variants if isinstance(_w[i], ProductTypeDict.MultiWord) else [])
                        if len(v[i]) > 1:
                            # For MultiWord add optional combinations with itself
                            v.append(v[i] + [u''])
                    for wv in product(*v):
                            if any(w_pair[0] == w_pair[1] or
                                    (isinstance(w_pair[0], ProductTypeDict.MultiWord) and w_pair[1] in w_pair[0].variants) or
                                    is_proposition_form(w_pair[0], w_pair[1])
                                    for w_pair in permutations(chain(wvf, wv), 2)):
                                # Do not join same world and form with proposition
                                continue
                            result[ProductType(*filter(len, chain(wvf, wv)))] = sqn

        add_combinations(words1, 0)
        if words1:
            add_combinations(words1, 1)
            add_combinations(words1, 2)

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
    def collect_type_tuples(products, verbose=False):
        """
        Collect product type tuples for all parsed products using @collect_sqn_type_tuples
        @param collections.Iterable[Product] products: sequence of Products
        @rtype: dict of (ProductType, list[unicode])
        """
        result = dict()
        i_count = 0
        if verbose:
            print u'Collecting type tuples from products'
        for product in products:
            product_tuples = ProductTypeDict.collect_sqn_type_tuples(product.sqn)

            for tag in product.get('tags', []):
                product_tuples[ProductType(u'#' + tag.lower())] = product.sqn

            for type_tuple, sqn in product_tuples.iteritems():
                existing_sqns = result.get(type_tuple, [])
                existing_sqns.append(sqn)
                result[type_tuple] = existing_sqns
            i_count += 1
            if verbose and i_count % 100 == 0: print u'.',
        if verbose:
            print
        return result

    @staticmethod
    def update_type_tuples_relationship(type_tuples, verbose=False, cleanup_prev_relations=True):
        """
        Calculate all non-repeatable combinations of type tuples with capacity not less than MIN_TUPLE_CAPACITY
        and check if one tuple is equals or contains (in terms of sqn set) another.
        NOTE: If type_tuples is big (10+K types) or/and TYPE_TUPLE_MIN_CAPACITY is too low (3 or less) this operation
        can work WAY TOO LONG. Be careful.
        @param dict of (ProductType, list[unicode]) type_tuples: from collect_type_tuples()
        @param bool verbose: type progress if specified - useful for testing of low capacity huge combinations
        """

        if verbose:
            print u'Updating type tuples relationships'

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
            else:
                s_inter = s1.intersection(s2)
                def similarity(s): return (round(1.0 * len(s_inter)/len(s), 2), len(s_inter))
                # if similarity(s1) >= 0.8:
                if len(s_inter) >= TYPE_TUPLE_MIN_CAPACITY:
                    # AKA setratio()>0.8 in Levenshtein
                    type1.almost(type2, similarity(s1), similarity(s2))
                # if similarity(s2) >= 0.8:
                if len(s_inter) >= TYPE_TUPLE_MIN_CAPACITY:
                    type2.almost(type1, similarity(s2), similarity(s1))

            if len(type1) == len(type2) and not type1.get_relation(type2):
                similarity = Levenshtein.setratio(type1, type2)
                if similarity >= 0.85:
                    # Is it too smart??
                    type1.similar(type2, round(similarity, 2))

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
        type_tuples = self.collect_type_tuples(products, verbose=self.VERBOSE)
        self.update_type_tuples_relationship(type_tuples, verbose=self.VERBOSE)
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

    def to_json(self, json_filename):
        """
        Persist type structures to JSON file
        @return:
        """
        types = {unicode(k): [len(set(sqns))]+[unicode(rel) for rel in k.relations()]
                 for k, sqns in self._type_tuples.iteritems()
                 if len(sqns) >= TYPE_TUPLE_MIN_CAPACITY or k.relations() or len(k) == 1
                 }

        with open(json_filename, 'wb') as f:
            f.truncate()
            f.write(json.dumps(types,
                               ensure_ascii=False,
                               check_circular=True,
                               indent=4).encode("utf-8"))
        if self.VERBOSE:
            print "Dumped json of %d type tuples to %s" % (len(types), json_filename)


def dump_json():
    config = main_options(sys.argv)
    products = Product.from_meta_csv(config['products_meta_in_csvname'])
    types = ProductTypeDict()
    types.VERBOSE = True
    types.build_from_products(products)
    types.to_json('out/product_types.json')


def print_sqn_tails():
    config = main_options(sys.argv)
    products = Product.from_meta_csv(config['products_meta_in_csvname'])
    types = ProductTypeDict()
    types.VERBOSE = True
    types.build_from_products(products)

    s = dict()
    s_type = dict()
    for t, sqns in sorted(types._type_tuples.iteritems(), key=lambda _t: len(_t[0])*100 + len(unicode(_t[0])), reverse=True):
        if len(t) == 1 or len(sqns) >= TYPE_TUPLE_MIN_CAPACITY or t.relations():
            for sqn in sqns:
                s[sqn] = s.get(sqn, sqn)
                for w in t:
                    sqn_replace = (u' ' + s[sqn] + u' ').replace(u' ' + w + u' ', u' ').strip()
                    if sqn_replace != s[sqn]:
                        s[sqn] = sqn_replace
                        s_type[sqn] = s_type.get(sqn, set())
                        s_type[sqn].add(t)
    t_products = []
    for sqn, tail in sorted(s.iteritems(), key=lambda _t: _t[0]):
        print u'%s => %s, types: %s' % (sqn, tail, u' '.join(map(unicode, s_type[sqn])))
        if tail:
            t_products.append(Product(sqn=tail))

    tails = types.collect_type_tuples(t_products, verbose=types.VERBOSE)
    for t, s in sorted(tails.iteritems(), key=lambda _t: len(set(_t[1])), reverse=True):
        if len(set(s)) < 3: continue
        print u'%s: %s' % (t, len(set(s)))

if __name__ == '__main__':
    # print_sqn_tails()
    dump_json()