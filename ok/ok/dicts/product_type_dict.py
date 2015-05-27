# -*- coding: utf-8 -*-
from ast import literal_eval
from collections import OrderedDict, defaultdict
import csv
from itertools import product as iter_product, combinations, permutations, chain
import itertools
import json
import re
import Levenshtein
from ok.dicts import get_word_normal_form, main_options, remove_nbsp
from ok.dicts.product import Product
from ok.dicts.product_type import TYPE_TUPLE_PROPOSITION_LIST, \
    TYPE_TUPLE_PROPOSITION_AND_WORD_LIST, ProductType, TYPE_TUPLE_RELATION_CONTAINS, \
    TYPE_TUPLE_RELATION_EQUALS, TYPE_TUPLE_RELATION_SUBSET_OF

TYPE_TUPLE_MIN_CAPACITY = 4  # Number of SQNs covered by word combination


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
        # This is a cache of _type_tuples with filtered meaningful items only (see filter_meaningful_types())
        # It MUST be dropped always when _type_tuples is changed
        self._meaningful_type_tuples = None

        self._min_meaningful_type_capacity = TYPE_TUPLE_MIN_CAPACITY

    @property
    def min_meaningful_type_capacity(self):
        return self._min_meaningful_type_capacity

    @min_meaningful_type_capacity.setter
    def min_meaningful_type_capacity(self, min_meaningful_type_capacity):
        if self._min_meaningful_type_capacity != min_meaningful_type_capacity:
            self._min_meaningful_type_capacity = min_meaningful_type_capacity
            self._meaningful_type_tuples = None

    class MultiWord(unicode):
        # Multi-variant string. It has main representation but also additional variants which can be used for
        # combinations. Typical example is compound words separated by hyphen.

        def __init__(self, object=''):
            super(ProductTypeDict.MultiWord, self).__init__(object)
            self._variants = set()
            self._do_not_pair = set()

        @property
        def variants(self):
            return frozenset(self._variants)

        def add_variants(self, *variants):
            for v in variants:
                self._variants.add(v)
                # Do not pair word with own variants. However, variants can pair each other
                v._do_not_pair.add(self)
                self._do_not_pair.add(v)

        def clear_variants(self):
            self._variants.clear()

        def can_pair(self, w):
            return w not in self._do_not_pair

        def do_not_pair(self, *dnp):
            self._do_not_pair.update(dnp)


    @staticmethod
    def collect_sqn_type_tuples(sqn, with_spellings=True):
        """
        Return dict with tuples for combinations of tokens in each parsed sqn. Source sqn will be as value.
        Join propositions to next word to treat them as single token
        If multiple parsed products with identical sqns are present all them will be in the value list as duplicates.
        It is required to estimate "capacity" of tuple
        @param bool with_spellings: if True above combinations of words also produce combinations with different
            word spellings like morph.normal_form, synonyms etc
        @rtype: dict of (ProductType, unicode)
        """
        # TODO: Implement synonyms pre-processing for unfolding of abbreviations to normal forms
        synonyms = [
                    {u'охл', u'охлажденная'},
                    {u'сельдь', u'селедка'},
                    {u'олив', u'оливковое'},
                    ]  # First ugly implementation
        synonyms_index = {syn: syn_set for syn_set in synonyms for syn in syn_set}
        def add_synonyms(_w):
            # Already MultiWord - add its variants synonyms as well. Must go first to avoid infinite loop
            syns = set()
            """@type: set of ProductTypeDict.MultiWord"""
            for _v in set(_w.variants):
                _v = add_synonyms(_v)
                syns |= _v.variants - {_w}
                _v.clear_variants()  # We don't need recursive synonyms data

            if _w in synonyms_index:
                syns |= set(map(ProductTypeDict.MultiWord, synonyms_index[_w])) - {_w}

            else:
                # Try to guess about normal form of word and treat it as synonym
                _w_normal_form = get_word_normal_form(_w, strict=True)
                if _w != _w_normal_form:
                    syns.add(ProductTypeDict.MultiWord(_w_normal_form))

            _w.add_variants(*syns)

            # Do not pair word and its variants with word own synonyms
            [_v.do_not_pair(*syns) for _v in _w.variants]

            return _w

        result = dict()

        words = re.split(u'\s+', sqn)
        words1 = []
        buf = u''
        buf_count = 0
        prev_words_with_prop = []
        """@type: list[ProductTypeDict.MultiWord]"""
        for w in words:
            if w:
                w = ProductTypeDict.MultiWord(w)
                if w in TYPE_TUPLE_PROPOSITION_LIST and not buf:
                    buf = w  # join proposition to the next words
                    if w in TYPE_TUPLE_PROPOSITION_AND_WORD_LIST:
                        # Some propositions can participate also as words (e.g. when char O is used instead of number 0)
                        # Add such propositions as simple word
                        words1.append(w)
                    continue
                if buf:
                    if w == u'и':
                        # Ignore 'and' if already in proposition mode
                        continue

                    if w in TYPE_TUPLE_PROPOSITION_LIST:
                        # Break previous proposition sequence and start new
                        buf = w
                        buf_count = 0
                        [w_p.do_not_pair(*prev_words_with_prop) for w_p in prev_words_with_prop]
                        prev_words_with_prop = []
                        if w in TYPE_TUPLE_PROPOSITION_AND_WORD_LIST:
                            # See above comments about dual prop/word cases
                            words1.append(w)
                        continue

                    # Add both word variants with proposition and w/o.
                    w_with_prop = ProductTypeDict.MultiWord(buf + u' ' + w)
                    w.add_variants(w_with_prop)
                    prev_words_with_prop.append(w_with_prop)
                    buf_count += 1

                    if buf_count == 2:
                        buf = u''
                        buf_count = 0
                        [w_p.do_not_pair(*prev_words_with_prop) for w_p in prev_words_with_prop]
                        prev_words_with_prop = []
                    # Proposition is added itself as well
                    # words1.append(buf)
                if u'-' in w:
                    # Now it is important the order of words they are added to list. First word is most important in
                    # type detection. Thus, compound words must present meaningful part first
                    # TODO: implement compound terms (~) that can be compared separately but in result are always together
                    variants = set(map(ProductTypeDict.MultiWord, w.split(u'-')))
                    w.add_variants(*variants)

                if with_spellings:
                    w = add_synonyms(w)
                words1.append(w)
        if buf and buf_count == 0: words1.append(buf)

        def can_pair(w1, w2):
            """
            @param ProductTypeDict.MultiWord w1: word1
            @param ProductTypeDict.MultiWord w2: word1
            """
            return w1.can_pair(w2) and w2.can_pair(w1)

        words1 = list(OrderedDict.fromkeys(words1))
        first_word = words1.pop(0)

        def add_combinations(_words, n):
            vf = [[]]
            vf[0] = [first_word] + list(first_word.variants)
            if len(vf[0]) > 1:
                # For MultiWord add optional combinations with itself
                vf.append(vf[0] + [ProductTypeDict.MultiWord(u'')])
            for wvf in iter_product(*vf):
                for _w in combinations(_words, n):
                    v = [[]] * len(_w)
                    for i, _wi in enumerate(_w):
                        v[i] = [_w[i]] + list(_w[i].variants)
                        if len(v[i]) > 1:
                            # For MultiWord add optional combinations with itself
                            v.append(v[i] + [ProductTypeDict.MultiWord(u'')])
                    for wv in iter_product(*v):
                            if any(w_pair[0] == w_pair[1] or
                                    w_pair[1] in w_pair[0].variants or
                                    not can_pair(w_pair[0], w_pair[1])
                                    for w_pair in permutations(chain(wvf, wv), 2) if w_pair[0] and w_pair[1]):
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
    def collect_type_tuples(products, strict_products=False):
        """
        Collect product type tuples for all parsed products using @collect_sqn_type_tuples
        @param collections.Iterable[Product] products: sequence of Products
        @rtype: dict of (ProductType, list[unicode])
        @param bool strict_products: if True do not try to collect transformation of type spellings because they are
            considered as 100% correct types. It may happen when loading types form external knowledge bases
        """
        result = defaultdict(list)
        """@type: dict of (ProductType, list[unicode])"""
        i_count = 0
        if ProductTypeDict.VERBOSE:
            print u'Collecting type tuples from products'
        for product in products:
            product_tuples = ProductTypeDict.collect_sqn_type_tuples(product.sqn, with_spellings=not strict_products)

            for type_tuple, sqn in product_tuples.iteritems():
                result[type_tuple].append(sqn)

            i_count += 1
            if ProductTypeDict.VERBOSE and i_count % 100 == 0: print u'.',
        if ProductTypeDict.VERBOSE:
            print
            print u"Collected %d type tuples" % len(result)
        return result

    def filter_meaningful_types(self, types_iter):
        """
        Take iterator and return filtered iterator without types to be ignored for processing
        @param collections.Iterable[ProductType, list[unicode]] types_iter: iterator over product types dict items
        @rtype: collections.Iterable[ProductType, list[unicode]]
        """
        for p_type, data in types_iter:
            if p_type.meaningful or len(data) >= self.min_meaningful_type_capacity or len(p_type) == 1 or p_type.relations():
                yield p_type, data

    @staticmethod
    def find_relation(type1, set1, type2, set2, max_similarity, almost_min_size=1):
        """
        @param ProductType type1: type from
        @param set|None set1: data from - if empty do not compare data sets but types only
        @param ProductType type2: type to
        @param set|None set2: data to - if empty do not compare data sets but types only
        @param float max_similarity: similarity level required
        @rtype: None|ProductType.Relation
        @return new instance of Relation. It is not applied to real types, though
        """
        relation = None
        if type1 == type2 or list(type1) == list(type2):
            relation = type1.identical(type2, dont_change=True)
        elif not set1 or not set2:
            # No SQNs are provided (ignore sqn mode?). Compare types by their tuples only
            type1_token_set = set(type1)
            type2_token_set = set(type2)
            if type1_token_set == type2_token_set:
                # Same type tokens in different order
                relation = type1.equals_to(type2, dont_change=True)
            elif type1_token_set.issubset(type2_token_set):
                # Shortest tuple is more general type
                relation = type1.contains(type2, dont_change=True)
            elif type1_token_set.issuperset(type2_token_set):
                # Longest tuple is more detailed or precise type
                relation = type1.subset_of(type2, dont_change=True)
        elif set1 and set2 and len(set1) == 1 and len(set2) == 1:
            # Special optimization for building of dict from external product type sources loaded as singleton products
            sqn1 = next(set1.__iter__())
            sqn2 = next(set2.__iter__())
            if sqn1 == sqn2:
                relation = type1.equals_to(type2, dont_change=True)
        elif set1 and set2:
            if set1.issubset(set2):
                if len(set1) < len(set2):
                    relation = type1.subset_of(type2, dont_change=True)
                else:
                    relation = type1.equals_to(type2, dont_change=True)
            elif set2.issubset(set1):
                relation = type1.contains(type2, dont_change=True)
            else:
                s_inter = set1.intersection(set2)

                def similarity(s):
                    return (round(1.0 * len(s_inter) / len(s), 2), len(s_inter))

                # if similarity(s1) >= 0.8:
                if len(s_inter) >= almost_min_size:
                    # AKA setratio()>0.8 in Levenshtein
                    relation = type1.almost(type2, similarity(set1), similarity(set2), dont_change=True)
                    # if similarity(s2) >= 0.8:
                    # if len(s_inter) >= TYPE_TUPLE_MIN_CAPACITY:
                    # relation = type1.almost(type2, similarity(s1), similarity(s2))

        if len(type1) == len(type2) and not type1.get_relation(type2):
            similarity = Levenshtein.setratio(type1, type2)
            if similarity >= max_similarity:
                # Is it too smart??
                relation = type1.similar(type2, round(similarity, 2), dont_change=True)

        return relation

    def update_type_tuples_relationship(self, type_tuples):
        """
        Calculate all non-repeatable combinations of type tuples with capacity not less than MIN_TUPLE_CAPACITY
        and check if one tuple is equals or contains (in terms of sqn set) another.
        NOTE: If type_tuples is big (10+K types) or/and TYPE_TUPLE_MIN_CAPACITY is too low (3 or less) this operation
        can work WAY TOO LONG. Be careful.
        @param dict of (ProductType, list[unicode]) type_tuples: from collect_type_tuples()
        """

        if self.VERBOSE:
            print u'Updating type tuples relationships'

        import zlib

        def get_hash(t):
            """
            @param ProductType|tuple t: type
            @return: int hash
            """
            res = 0
            for i in sorted(t.get_terms_ids() if isinstance(t, ProductType) else t):
                res = zlib.adler32(str(i), res)
            return res

        seen_type_tuples = defaultdict(set)
        """@type: dict of (int, set[ProductType])"""
        if self._type_tuples:
            for t in self._type_tuples:
                seen_type_tuples[get_hash(t)].add(t)
        same_length_group = set()
        last_group_length = 0
        i_count = 0
        relations_created = 0
        for t, sqns in sorted(self.filter_meaningful_types(type_tuples.iteritems()), key=lambda _i: len(_i[0])):
            terms = t.get_terms_ids()
            terms_set = set(terms)
            for i in xrange(len(t)):
                for variant in itertools.combinations(terms, i+1):
                    v_hash_key = get_hash(variant)
                    # Contains & Equals - transitive
                    if v_hash_key in seen_type_tuples:
                        found_types = seen_type_tuples[v_hash_key]
                        if t in found_types:
                            continue
                        for f_type in found_types:
                            inter = terms_set.intersection(f_type.get_terms_ids())
                            t_is_more = len(terms) > len(inter)
                            f_is_more = len(f_type) > len(inter)
                            if f_is_more:
                                if not t_is_more:
                                    # Longest tuple is more detailed or precise type
                                    t.contains(f_type)
                                    relations_created += 1
                            elif t_is_more:
                                # Shortest tuple is more general type
                                t.subset_of(f_type)
                                relations_created += 1
                            else:
                                # Same type tokens in different order
                                t.equals_to(f_type)
                                relations_created += 1
                                # Transitive relation
                                # - if a equals b than b's children are a's children and vise verse
                                for f_sub in f_type.related_types(TYPE_TUPLE_RELATION_CONTAINS):
                                    t.contains(f_sub)
                                    relations_created += 1
                                for t_sub in t.related_types(TYPE_TUPLE_RELATION_CONTAINS):
                                    f_type.contains(t_sub)
                                    relations_created += 1

            if last_group_length != len(t):
                last_group_length = len(t)
                same_length_group = set()

            for sibling in same_length_group:
                if not t.get_relation(sibling):
                    similarity = Levenshtein.setratio(t, sibling)
                    if similarity >= 0.85:
                        # Is it too smart??
                        t.similar(sibling, round(similarity, 2))
                        relations_created += 1
            same_length_group.add(t)
            seen_type_tuples[get_hash(terms)].add(t)

            i_count += 1
            if self.VERBOSE and i_count % 100 == 0: print u'.',
            if self.VERBOSE and i_count % 10000 == 0: print i_count
        if self.VERBOSE: print
        if self.VERBOSE: print "Created %d relations" % relations_created
        pass

    def find_type_tuples_relationship(self, type_tuples, baseline_dict=None, ignore_sqns=False, force_deep_scan=False, max_similarity=0.8):
        """
        Calculate all non-repeatable combinations of type tuples with capacity not less than MIN_TUPLE_CAPACITY
        and check if one tuple is equals or contains (in terms of sqn set) another.
        NOTE: If type_tuples is big (10+K types) or/and TYPE_TUPLE_MIN_CAPACITY is too low (3 or less) this operation
        can work WAY TOO LONG. Be careful.
        @param dict of (ProductType, list[unicode]) type_tuples: from collect_type_tuples()
        @param dict of (ProductType, list[unicode]) baseline_dict: If specified try to find relations between type_tuples
                and some external dict data. If not specified - local existing meaningful dictionary data will be used.
                Using external dict data is useful for checking of some theories about not-persistent (virtual) data
        @param bool ignore_sqns: if True do not try to compare sqn data sets but check type tuples only
        @param bool force_deep_scan: if True scan for similarity all non-identical types even if identical has been found.
        @return: dict of ProductType mapped to suggested Relations linked to meaningful types in types dict.
                Relation instances are not in types actually and should be used for analysis or must be merged later
                if required to types data
        """

        # if self.VERBOSE:
        #     print u'Find type tuples relationships: %s' % (u', '.join(map(unicode, type_tuples.keys())))

        i_count = 0
        types_suggested_relations = defaultdict(list)
        """@type: dict of (ProductType, list[ProductType.Relation])"""

        type_tuples_for_deep_scan = dict(type_tuples)
        dict_types = baseline_dict or self.get_type_tuples(meaningful_only=True)
        if ignore_sqns:
            # Optimize lookup data set - do not iterate for known types, just map as identical
            for t in type_tuples:
                if t in dict_types:
                    # Must always find identical relation
                    rel = self.find_relation(t, None, t, None, max_similarity, almost_min_size=self.min_meaningful_type_capacity)
                    types_suggested_relations[t].append(rel)
                    if force_deep_scan:
                        del type_tuples_for_deep_scan[t]

        if not force_deep_scan and types_suggested_relations:
            # If identical types have been found deep scan is not required
            type_tuples_for_deep_scan.clear()
            # if self.VERBOSE: print "Identical type 's been found, skip deep scan"

        for t1, t2 in iter_product(type_tuples_for_deep_scan.iteritems(), dict_types.iteritems()):
            s1 = set(t1[1]) if not ignore_sqns else None
            s2 = set(t2[1]) if not ignore_sqns else None
            type_input = t1[0]
            """@type: ProductType"""
            type_dict = t2[0]
            """@type: ProductType"""

            rel = self.find_relation(type_input, s1, type_dict, s2, max_similarity,almost_min_size=self.min_meaningful_type_capacity)

            if rel:
                types_suggested_relations[type_input].append(rel)

            i_count += 1
            if self.VERBOSE and i_count % 10000 == 0: print u'.',
            if self.VERBOSE and i_count % 1000000 == 0: print i_count
        if self.VERBOSE and i_count >= 10000:
            print
            # print u'Suggested %d types' % len(types_suggested_relations)

        return types_suggested_relations

    def build_tag_types_from_products(self, products, type_tuples):
        tag_type_relation_variants = defaultdict(set)
        """@type: dict of (ProductType, set[ProductType])"""
        sqn_types = defaultdict(set)
        """@type: dict of (unicode, set[ProductType])"""
        for t, sqns in self.filter_meaningful_types(type_tuples.iteritems()):
            for sqn in sqns:
                sqn_types[sqn].add(t)
        for product in products:
            for tag in product.get('tags', set()):
                tag_type = ProductType(u'#' + tag.lower())
                tag_type_relation_variants[tag_type].update(sqn_types[product.sqn])
                type_tuples[tag_type].append(product.sqn)
        for tag_type, relation_to_variants in tag_type_relation_variants.iteritems():
            for t in relation_to_variants | set(tag_type_relation_variants.keys()):
                # Check relations through products as well as between all tag types
                t = t
                """@type: ProductType"""
                if t == tag_type:
                    continue
                # Parent tag type must contains all sqns of type as well as all its transitive relations
                t_sqn_set = set()
                [t_sqn_set.update(type_tuples[tt]) for tt in [t] + t.related_types(TYPE_TUPLE_RELATION_EQUALS, TYPE_TUPLE_RELATION_CONTAINS)]
                tag_sqn_set = set(type_tuples[tag_type])
                if tag_sqn_set == t_sqn_set:
                    tag_type.equals_to(t)
                elif tag_sqn_set.issubset(t_sqn_set):
                    tag_type.subset_of(t)
                elif tag_sqn_set.issuperset(t_sqn_set):
                    tag_type.contains(t)
                # TODO - implement 'almost' relation

    def build_from_products(self, products, strict_products=False):
        """
        Build types graph from sequence of products
        @param collections.Iterable[Product] products: iterator of Product
        @param bool strict_products: see comments for collect_type_tuples()
        """
        p_it1, p_it2 = itertools.tee(products)
        type_tuples = self.collect_type_tuples(p_it1, strict_products=strict_products)
        self.update_type_tuples_relationship(type_tuples)

        self.build_tag_types_from_products(p_it2, type_tuples)

        if not self._type_tuples:
            self._type_tuples = type_tuples
        else:
            # merge
            for t, sqns in type_tuples.iteritems():
                self._type_tuples[t].extend(sqns)
                # TODO: Update tag types as well - new sqns may add or break old tag type relations
        self._meaningful_type_tuples = None
        return self._type_tuples

    def get_type_tuples(self, meaningful_only=False):
        """
        @return dict of ProductTypes
        @rtype: dict of (ProductType, list[unicode])
        """
        if not self._type_tuples:
            raise Exception("You have to build dict first!")
        if not meaningful_only:
            return dict(self._type_tuples)
        else:
            if not self._meaningful_type_tuples:
                self._meaningful_type_tuples = dict((k, v) for k, v in self.filter_meaningful_types(self._type_tuples.iteritems()))
            return self._meaningful_type_tuples

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
        """
        types = OrderedDict((unicode(k), [len(set(sqns))]+[unicode(rel) for rel in k.relations()])
                            for k, sqns in sorted(self.get_type_tuples(meaningful_only=True).iteritems(), key=lambda _t: unicode(_t[0]))
                            )

        with open(json_filename, 'wb') as f:
            f.truncate()
            f.write(json.dumps(types,
                               ensure_ascii=False,
                               check_circular=True,
                               indent=4).encode("utf-8"))
        if self.VERBOSE:
            print "Dumped json of %d type tuples to %s" % (len(types), json_filename)

    def from_json(self, json_filename):
        """
        Restore type structures from JSON file (see format in to_json)
        SQNs cannot be restored from type dump and should be updated separately if required. For API compatibility
        they are filled as lists of indexes with len from dump
        """
        with open(json_filename, 'rb') as f:
            s = f.read().decode("utf-8")
        types = json.loads(s)
        ProductType.reload()
        type_tuples = dict()
        pseudo_sqn = 1
        seen_rel = dict()
        for type_str, rel_str in types.iteritems():
            type_items = type_str.split(u' + ')
            pt = ProductType(*type_items, meaningful=True)
            type_tuples[pt] = []
            for i in xrange(int(rel_str[0])):
                type_tuples[pt].append(unicode(pseudo_sqn))
                pseudo_sqn += 1

            for r_str in rel_str[1:]:
                r_match = re.findall(u'^(\w+)(?:\[([^\]]+)\])?(~)?\s+(.*)$', r_str)
                if r_match:
                    relation, rel_attr, is_soft, type_to_str = r_match[0]
                    type_to_items = type_to_str.split(u' + ')
                    type_to = ProductType(*type_to_items, meaningful=True)
                    if rel_attr:
                        try:
                            rel_attr = literal_eval(rel_attr)
                        except ValueError:
                            pass  # Just use string as is
                    r_to = ProductType.Relation(from_type=pt, to_type=type_to, rel_type=relation, is_soft=is_soft == u'~', rel_attr=rel_attr)
                    if type_to in seen_rel and pt in seen_rel[type_to]:
                        # Already processed back relation
                        r_from = seen_rel[type_to][pt]
                        pt.make_relation(type_to, r_to.rel_type, r_from.rel_type, r_to.is_soft, r_to.rel_attr, r_from.rel_attr)
                    else:
                        seen_rel[pt] = seen_rel.get(pt, dict())
                        seen_rel[pt][type_to] = r_to
        self._type_tuples = type_tuples
        self._meaningful_type_tuples = None

        if self.VERBOSE:
            print "Loaded %d type tuples from json %s" % (len(self._type_tuples), json_filename)


def dump_json():
    config = main_options(sys.argv)
    products = Product.from_meta_csv(config.products_meta_in_csvname)
    types = ProductTypeDict()
    ProductTypeDict.VERBOSE = True
    types.build_from_products(products)
    types.to_json('out/product_types_2.json')


def load_from_json():
    config = main_options(sys.argv)
    types = ProductTypeDict()
    types.VERBOSE = True
    types.from_json(config.product_types_in_json)
    types.to_json('out/product_types_1.json')
    products_meta_in_csvname = config.products_meta_in_csvname
    if products_meta_in_csvname:
        products = list(Product.from_meta_csv(products_meta_in_csvname))
        type_tuples = types.get_type_tuples()
        meaningful_tuples = set(type_tuples)
        for p in products:
            p_all_types = types.collect_sqn_type_tuples(p.sqn)
            type_variants = set(p_all_types)
            p_all_types2 = types.collect_sqn_type_tuples(u'-'.join(p.sqn.split(u' ', 1)))
            type_variants.update(p_all_types2)
            p_types = type_variants.intersection(meaningful_tuples)
            p['types'] = p_types

        products_meta_out_csvname = config.products_meta_out_csvname
        if products_meta_out_csvname:
            Product.to_meta_csv(products_meta_out_csvname, products)

def from_hdiet_csv(prodcsvname):
    """
    Load and pre-parse products raw data from HDiet crawler
    @type prodcsvname: str
    @return:
    """
    from ok.dicts.prodproc import ProductFQNParser
    products = []
    with open(prodcsvname, "rb") as f:
        reader = csv.reader(f)
        fields = next(reader)
        parser = ProductFQNParser()
        for row in reader:
            prodrow = dict(zip(fields, row))
            item = dict(prodrow)
            pfqn = remove_nbsp(unicode(item["name"], "utf-8"))

            top_cat = None
            sub_cat = None
            if item.get("details"):
                details_raw = remove_nbsp(item["details"])
                details = json.loads(details_raw)
                """ @type details: dict of (unicode, unicode) """

                top_cat = details.get('top_cat')
                sub_cat = details.get('sub_cat')

            if top_cat.lower() == u'Алкогольные напитки'.lower():
                continue

            product = parser.extract_product(pfqn)
            product['tags'] = {cat for cat in (top_cat, sub_cat) if cat}
            products.append(product)

    types = ProductTypeDict()
    ProductTypeDict.VERBOSE = True
    types.min_meaningful_type_capacity = 1
    type_tuples = types.build_from_products(products, strict_products=True)
    for t in type_tuples:
        t.meaningful = True
    types.to_json('out/product_types_hdiet.json')

    config = main_options(sys.argv)
    products = Product.from_meta_csv(config.products_meta_in_csvname)
    products, len_p = itertools.tee(products)
    print("Try to merge generated types from meta: %d products" % len(list(len_p)))
    types.min_meaningful_type_capacity = TYPE_TUPLE_MIN_CAPACITY
    type_tuples = types.build_from_products(products)
    types.to_json('out/product_types_merged.json')
    print("Total types after merge: %d/%d" % (len(type_tuples), len(types.get_type_tuples(meaningful_only=True))))

    ProductType.print_stats()

def print_sqn_tails():
    config = main_options(sys.argv)
    products = Product.from_meta_csv(config.products_meta_in_csvname)
    types = ProductTypeDict()
    types.VERBOSE = True
    types.build_from_products(products)

    s = dict()
    s_type = dict()
    for t, sqns in sorted(types.get_type_tuples().iteritems(), key=lambda _t: len(_t[0])*100 + len(unicode(_t[0])), reverse=True):
        if len(t) == 1 or len(sqns) >= types.min_meaningful_type_capacity or t.relations():
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

    tails = types.collect_type_tuples(t_products)
    for t, s in sorted(tails.iteritems(), key=lambda _t: len(set(_t[1])), reverse=True):
        if len(set(s)) < 3: continue
        print u'%s: %s' % (t, len(set(s)))

if __name__ == '__main__':
    import sys
    # print_sqn_tails()
    # dump_json()
    load_from_json()

    # from_hdiet_csv(sys.argv[1])