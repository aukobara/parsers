# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals

from ast import literal_eval
from collections import OrderedDict, defaultdict
import csv
import itertools
import json
import re

import Levenshtein
from jsmin import jsmin
from ok.dicts import to_str

from ok.dicts.product import Product
from ok.dicts.product_type import ProductType,\
    TYPE_TUPLE_RELATION_CONTAINS, TYPE_TUPLE_RELATION_EQUALS, TYPE_TUPLE_RELATION_SUBSET_OF, EqWrapper
from ok.dicts.term import TypeTerm, CompoundTypeTerm, WithPropositionTypeTerm, TagTypeTerm, TypeTermException, \
    ContextRequiredTypeTermException, ContextDependentTypeTerm

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
        self._type_tuples = defaultdict(list)
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
        result = dict()

        terms = TypeTerm.parse_term_string(sqn)
        context = terms[:]
        first_word = terms.pop(0)

        def get_term_with_sub_terms(term, context):
            term_list = {term}
            if isinstance(term, CompoundTypeTerm):
                term_list.update(term.sub_terms)
            if with_spellings:
                term_list.update([wf for t in term_list for wf in t.word_forms(context=context, fail_on_context=False)])

            return term_list

        def make_product_type(pt_terms):
            pt_type = None
            try:
                # Validate product type terms are can produce normal final type
                ProductType.calculate_same_same_hash(pt_terms)
                pt_type = ProductType(*pt_terms)
            except TypeTermException:
                # Something wrong with terms (context are not full?). Skip combination
                pass
            return pt_type

        def add_result(pt_terms):
            pt_type = make_product_type(pt_terms)
            if pt_type:
                result[pt_type] = sqn
            # Also add type with expanded compound terms
            if any(isinstance(pt, CompoundTypeTerm) for pt in pt_terms):
                exp_terms = []
                for pt in pt_terms:
                    if isinstance(pt, CompoundTypeTerm) and len(pt.simple_sub_terms) > 1:
                        exp_terms.extend(pt.simple_sub_terms)
                    else:
                        exp_terms.append(pt)
                if len(exp_terms) > len(pt_terms):
                    # Found type with more terms
                    pt_type = make_product_type(exp_terms)
                    if pt_type:
                        result[pt_type] = sqn

        def add_combinations(_terms, n, _context):
            vf = [[]]
            vf[0] = get_term_with_sub_terms(first_word, _context)
            for wvf in itertools.product(*vf):
                for _w in itertools.combinations(_terms, n):
                    v = [[]] * len(_w)
                    for i, _wi in enumerate(_w):
                        v[i] = get_term_with_sub_terms(_w[i], _context)
                    for wv in itertools.product(*v):
                        pt_terms = wvf + wv
                        if any(not w_pair[0].is_compatible_with(w_pair[1], context=_context) or
                                       not w_pair[1].is_compatible_with(w_pair[0], context=_context)
                                for w_pair in itertools.permutations(pt_terms, 2) if w_pair[0] and w_pair[1]):
                            # Do not join words that cannot be paired (like word and the same word with proposition)
                            continue
                        add_result(pt_terms)

        add_combinations(terms, 0, context)
        if len(terms) > 0:
            add_combinations(terms, 1, context)
        if len(terms) > 1:
            add_combinations(terms, 2, context)

        return result

    # TODO: make this cache more general and manageable. Merge this cache logic with update_relationship()
    __main_form_cache = None
    """@type __main_form_cache: dict of (set, set[ProductType])"""

    @staticmethod
    def _main_form_key(p_type):
        """
        @param ProductType|list[int] p_type: product type or list of type term ids
        """
        term_ids = p_type.get_main_form_term_ids() if isinstance(p_type, ProductType) else p_type
        return frozenset(term_ids)

    __similarity_groups_cache = None

    @staticmethod
    def _similarity_hash_key(p_type):
        chars = []
        for term in p_type:
            meaningful_word = term
            if isinstance(term, WithPropositionTypeTerm):
                meaningful_word = term.sub_terms[0]
            elif isinstance(term, TagTypeTerm):
                meaningful_word = term.replace(u'#', '')
            chars.append(meaningful_word[0])
        return frozenset(chars)

    def _ensure_find_caches(self):
        if self.__main_form_cache is None or self.__similarity_groups_cache is None:
            all_types = self.get_type_tuples(meaningful_only=True)
            self.__main_form_cache = defaultdict(set)
            """@type dict of (set, set[ProductType])"""
            self.__similarity_groups_cache = defaultdict(set)
            for p_type in all_types:
                try:
                    self.__main_form_cache[self._main_form_key(p_type)].add(p_type)
                except ContextRequiredTypeTermException:
                    # Bad non-final type detected. What to do?
                    # TODO: ignore? or cache with all variants?
                    terms_matrix = [term.all_context_main_forms() if isinstance(term, ContextDependentTypeTerm)
                                    else [term.get_main_form()] for term in p_type]
                    for term_variants in itertools.product(*terms_matrix):
                        term_ids = [term.term_id for term in term_variants]
                        self.__main_form_cache[self._main_form_key(term_ids)].add(p_type)

                self.__similarity_groups_cache[self._similarity_hash_key(p_type)].add(p_type)

    # Not supported for a while. Deprecated
    def find_product_types(self, sqn, with_spellings=True):
        product_types = self.collect_sqn_type_tuples(sqn, with_spellings=with_spellings)

        self._ensure_find_caches()

        result = set()
        for p_type in product_types:
            result.update(self.__main_form_cache.get(self._main_form_key(p_type), []))

        return result

    def find_product_type_relations(self, sqn, with_spellings=True):
        self._ensure_find_caches()

        tag_type = None
        if TagTypeTerm.is_valid_term_for_type(sqn):
            tag_type = ProductType(sqn.lower(), singleton=False)
            product_types = {tag_type: sqn}
        else:
            product_types = self.collect_sqn_type_tuples(sqn, with_spellings=with_spellings)

        if not tag_type:
            # Try tag type as well. Now, naive version when try to match whole string as tag
            # Probably better place for such thing is caller business logic
            tag_key = self._main_form_key(ProductType(u'#' + sqn.lower(), singleton=False))
            tag_types_set = self.__main_form_cache.get(tag_key, set())
            tag_type = next(iter(tag_types_set), None)
            if tag_type:
                product_types[tag_type] = sqn

        result = defaultdict(list)
        """@type: dict of (ProductType, list[ProductType.Relation])"""
        for t in product_types:
            t_key = self._main_form_key(t)
            types_exist = self.__main_form_cache.get(t_key, set())
            for t_sibling in product_types:
                # Check relations between parsed types as well even if they are not in types dict
                if t_sibling != t and t_sibling not in types_exist and self._main_form_key(t_sibling) == t_key:
                    types_exist.add(t_sibling)
            seen_related = set()
            for t2 in types_exist:
                r = t.get_relation(t2)
                if not r:
                    r = t.equals_to(t2, dont_change=True)
                result[t].append(r)
                result[t].extend(t2.relations())
                seen_related.add(t2)
                seen_related.update(_r.to_type for _r in t2.relations())
            similarity_group = self.__similarity_groups_cache.get(self._similarity_hash_key(t), [])
            for st in similarity_group:
                if st not in seen_related:
                    r = self.find_similar_relation(t, st, dont_change=True)
                    if r:
                        result[t].append(r)
                        result[t].extend(st.relations())
                        seen_related.add(st)
                        seen_related.update(_r.to_type for _r in st.relations())
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
            print(u'Collecting type tuples from products')
        for product in products:
            product_tuples = ProductTypeDict.collect_sqn_type_tuples(product.sqn, with_spellings=not strict_products)

            for type_tuple, sqn in product_tuples.viewitems():
                result[type_tuple].append(sqn)

            i_count += 1
            if ProductTypeDict.VERBOSE and i_count % 100 == 0: print(u'.', end='')
        if ProductTypeDict.VERBOSE:
            print()
            print(u"Collected %d type tuples" % len(result))
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
    def compare_types(t1, t2, max_similarity=0):
        """
        @param ProductType t1: type from
        @param ProductType t2: type to
        @param float max_similarity: similarity level required
        @rtype: None|ProductType.Relation
        @return new instance of Relation. It is not applied to real types, though
        """
        relation = None
        if t1 == t2 or list(t1) == list(t2):
            relation = t1.identical(t2, dont_change=True)
        else:
            t1_terms_set = frozenset(t1.get_main_form_term_ids())
            t2_terms_set = frozenset(t2.get_main_form_term_ids())
            inter = t1_terms_set.intersection(t2_terms_set)
            t1_is_more = len(t1_terms_set) > len(inter)
            t2_is_more = len(t2_terms_set) > len(inter)
            if t2_is_more:
                if not t1_is_more:
                    # Longest tuple is more detailed or precise type
                    relation = t1.contains(t2, dont_change=True)
            elif t1_is_more:
                # Shortest tuple is more general type
                relation = t1.subset_of(t2, dont_change=True)
            elif t1 != t2:
                # Same type terms in different order
                relation = t1.equals_to(t2, dont_change=True)

            if max_similarity and not relation:
                relation = ProductTypeDict.find_similar_relation(t1, t2, max_similarity, dont_change=True)

        return relation

    @staticmethod
    def find_similar_relation(p_type1, p_type2, max_similarity=0.85, dont_change=False):
        relation = None
        similarity = 0
        if not p_type1.get_relation(p_type2):
            if len(p_type1) == len(p_type2):
                similarity = Levenshtein.setratio(p_type1, p_type2)
            if len(p_type1) > 1:
                similarity = max(similarity, Levenshtein.ratio(p_type1.as_string(), p_type2.as_string()))
            if similarity >= max_similarity:
                # Is it too smart??
                relation = p_type1.similar(p_type2, round(similarity, 2), dont_change=dont_change)
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
            print(u'Updating type tuples relationships')

        seen_type_tuples = defaultdict(set)
        """@type: dict of (int, set[ProductType])"""
        if self._type_tuples:
            for t in self._type_tuples:
                seen_type_tuples[t.get_same_same_hash()].add(t)
        same_length_group = defaultdict(list)
        last_group_length = 0
        i_count = 0
        relations_created = 0
        for t, sqns in sorted(self.filter_meaningful_types(type_tuples.viewitems()), key=lambda _i: len(_i[0])):
            terms = t.get_terms_ids()
            main_form_terms_set = set(t.get_main_form_term_ids())
            for i in range(len(t)):
                for variant in itertools.combinations(terms, i+1):
                    v_hash_key = ProductType.calculate_same_same_hash(variant)
                    # Contains & Equals - transitive
                    if v_hash_key in seen_type_tuples:
                        found_types = seen_type_tuples[v_hash_key]
                        for f_type in found_types:
                            inter = main_form_terms_set.intersection(f_type.get_main_form_term_ids())
                            t_is_more = len(terms) > len(inter)
                            f_is_more = len(f_type) > len(inter)
                            r = None
                            if f_is_more:
                                if not t_is_more:
                                    # Longest tuple is more detailed or precise type
                                    r = t.contains(f_type)
                            elif t_is_more:
                                # Shortest tuple is more general type
                                r = t.subset_of(f_type)
                            elif t != f_type:
                                # Same type terms in different order
                                r = t.equals_to(f_type)
                                # Transitive relation
                                # - if a equals b than b's children are a's children and vise verse
                                for f_sub in f_type.related_types(TYPE_TUPLE_RELATION_CONTAINS):
                                    t.contains(f_sub)
                                    relations_created += 1
                                for t_sub in t.related_types(TYPE_TUPLE_RELATION_CONTAINS):
                                    f_type.contains(t_sub)
                                    relations_created += 1
                            if r: relations_created += 1

            if last_group_length != len(t):
                last_group_length = len(t)
                same_length_group.clear()

            # Group terms with the same first char only
            # TODO: optimize selection of group - actually first chars may have similar spellings as well (like е and ё)
            similarity_hash_key = frozenset({_term[0] if not isinstance(_term, WithPropositionTypeTerm) else _term.sub_terms[0][0] for _term in t})
            for sibling in same_length_group.get(similarity_hash_key, []):
                r = self.find_similar_relation(t, sibling)
                if r: relations_created += 1
            same_length_group[similarity_hash_key].append(t)

            seen_type_tuples[t.get_same_same_hash()].add(t)

            i_count += 1
            if self.VERBOSE and i_count % 100 == 0: print(u'.', end='')
            if self.VERBOSE and i_count % 10000 == 0: print(i_count)
        if self.VERBOSE: print()
        if self.VERBOSE: print("Created %d relations" % relations_created)
        pass

    # DEPRECATED
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
                    rel = self.compare_types(t, t)
                    types_suggested_relations[t].append(rel)
                    if force_deep_scan:
                        del type_tuples_for_deep_scan[t]

        if not force_deep_scan and types_suggested_relations:
            # If identical types have been found deep scan is not required
            type_tuples_for_deep_scan.clear()
            # if self.VERBOSE: print "Identical type 's been found, skip deep scan"

        for t1, t2 in itertools.product(type_tuples_for_deep_scan.viewitems(), dict_types.viewitems()):
            type_input = t1[0]
            """@type: ProductType"""
            type_dict = t2[0]
            """@type: ProductType"""

            rel = self.compare_types(type_input, type_dict, max_similarity)

            if rel:
                types_suggested_relations[type_input].append(rel)

            i_count += 1
            if self.VERBOSE and i_count % 10000 == 0: print(u'.', end='')
            if self.VERBOSE and i_count % 1000000 == 0: print(i_count)
        if self.VERBOSE and i_count >= 10000:
            print()
            # print u'Suggested %d types' % len(types_suggested_relations)

        return types_suggested_relations

    def build_tag_types_from_products(self, products, type_tuples):
        if self.VERBOSE:
            print(u"Building tag types from product's data")

        tag_type_relation_variants = defaultdict(set)
        """@type: dict of (ProductType, set[ProductType])"""
        sqn_types = defaultdict(set)
        """@type: dict of (unicode, set[ProductType])"""
        for t, sqns in self.filter_meaningful_types(type_tuples.viewitems()):
            for sqn in sqns:
                sqn_types[sqn].add(t)
        for product in products:
            for tag in product.get('tags', set()):
                tag_type = ProductType(u'#' + tag.lower())
                # Collect all types of tagged products
                tag_type_relation_variants[tag_type].update(sqn_types[product.sqn])
                if product.sqn not in type_tuples[tag_type]:
                    type_tuples[tag_type].append(product.sqn)

        new_relations = []
        """@type list[ProductType.Relation]"""
        updating_tag_types = set(tag_type_relation_variants.keys())
        for tag_type, relation_to_variants in tag_type_relation_variants.viewitems():
            for t in relation_to_variants | updating_tag_types:
                # Check relations through products as well as between all tag types
                t = t
                """@type: ProductType"""
                if t == tag_type:
                    continue
                t_sqn_set = set(type_tuples[t])
                # Parent tag type must contains all sqns of type as well as all its transitive relations
                # However, do not take into consideration other tag types which will be updated in this loop
                [t_sqn_set.update(type_tuples[tt])
                    for tt in t.related_types(TYPE_TUPLE_RELATION_EQUALS, TYPE_TUPLE_RELATION_CONTAINS)
                    if tt != t and tt not in updating_tag_types
                 ]
                tag_sqn_set = set(type_tuples[tag_type])
                r = None
                # First remove old relation
                # TODO: Understand how to merge such situation. Now just break old relation and create new if exist
                tag_type.not_related(t)

                # Than, try to find new one
                inter_set = tag_sqn_set.intersection(t_sqn_set)
                common_sqns_num = len(inter_set)
                tag_is_more = len(tag_sqn_set) > common_sqns_num
                t_is_more = len(t_sqn_set) > common_sqns_num
                if tag_is_more:
                    if not t_is_more:
                        r = tag_type.contains(t, dont_change=True)
                    elif common_sqns_num > 0:
                        # Types are not contain each other but have intersection
                        # Calculate sqn sets similarity
                        tag_similarity = round(1.0 * common_sqns_num / len(tag_sqn_set), 2)
                        t_similarity = round(1.0 * common_sqns_num / len(t_sqn_set), 2)
                        if tag_similarity > 0 and t_similarity > 0:
                            r = tag_type.almost(t, tag_similarity, t_similarity, dont_change=True)
                elif t_is_more:
                    r = tag_type.subset_of(t, dont_change=True)
                else:
                    r = tag_type.equals_to(t, dont_change=True)

                # TODO - implement 'almost' relation
                if r:
                    new_relations.append(r)
            if self.VERBOSE and len(new_relations) % 10 == 0: print(u'.', end='')

        tags_created = set()
        for r in new_relations:
            tag_type = r.from_type
            tag_type.copy_relation(r)
            tags_created.add(tag_type)

        if self.VERBOSE:
            print()
            print(u"Tag types created %d with %d relations" % (len(tags_created), len(new_relations)))

    def build_from_products(self, products, strict_products=False):
        """
        Build types graph from sequence of products
        @param collections.Iterable[Product] products: iterator of Product
        @param bool strict_products: see comments for collect_type_tuples()
        """
        p_it1, p_it2 = itertools.tee(products)

        # 1. Collect all possible type variants. Those are already in dict as meaningful existing types
        # matches as singleton ProductType with meaningful flag
        type_tuples = self.collect_type_tuples(p_it1, strict_products=strict_products)

        # 2. Find and update relations of types produced by products. Already existing meaningful types
        # will be linked to new types
        self.update_type_tuples_relationship(type_tuples)

        # 3. Build tag types basing on their relation with products. I.e. matching set will be restricted by types
        # of products which have tag instead of type terms as for normal type
        self.build_tag_types_from_products(p_it2, type_tuples)

        # 4. Merge new types to existing
        for t, sqns in type_tuples.viewitems():
            wrapper = EqWrapper(t)
            if wrapper in self._type_tuples and wrapper.match:
                assert wrapper.match is t, \
                    "Meet product type duplicate instance! Validate your ProductType singleton cache: %s" % to_str(t)
            self._type_tuples[t].extend(sqns)
            # TODO: Update tag types as well - new sqns may add or break old tag type relations
        # Clear meaningful types cache
        self._meaningful_type_tuples = None

        # 5. Keep most meaningful synonym types only
        # TODO

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
                self._meaningful_type_tuples = dict((k, v) for k, v in self.filter_meaningful_types(self._type_tuples.viewitems()))
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
        types = OrderedDict()
        type_tuples = self.get_type_tuples(meaningful_only=True)
        for k, sqns in sorted(type_tuples.viewitems(), key=lambda _t: to_str(_t[0])):
            sqns_in_self_num = len(set(sqns))
            sqns_under_num = len(set(sqn for tt in [k] + k.related_types(TYPE_TUPLE_RELATION_EQUALS,
                                                                         TYPE_TUPLE_RELATION_CONTAINS)
                                     for sqn in type_tuples[tt]))
            types[to_str(k)] = ['%d/%d' % (sqns_in_self_num, sqns_under_num)] + [to_str(rel) for rel in k.relations()]

        with open(json_filename, 'wb') as f:
            f.truncate()
            f.write(json.dumps(types,
                               ensure_ascii=False,
                               check_circular=True,
                               indent=4).encode("utf-8"))

        """
        pd_hdiet = ProductTypeDict()
        pd_hdiet.min_meaningful_type_capacity = 1
        pd_hdiet.from_json(build_path(ensure_baseline_dir(), 'product_types_hdiet.json', None), dont_change=True)
        hdiet_types = pd_hdiet.get_type_tuples()

        with open(json_filename + '.~', 'wb') as f:
            f.truncate()
            f.write('\r\n'.join(to_str(t).encode('utf-8') + ('[hdiet]' if t in hdiet_types else '')
                                for t, v in sorted(self.get_type_tuples(meaningful_only=True).viewitems(), key=lambda _t: to_str(_t[0]))))
        """
        if self.VERBOSE:
            print("Dumped json of %d type tuples to %s" % (len(types), json_filename))

    def from_json(self, json_filename, dont_change=False):
        """
        Restore type structures from JSON file (see format in to_json)
        SQNs cannot be restored from type dump and should be updated separately if required. For API compatibility
        they are filled as lists of indexes with len from dump
        @param bool dont_change: if True do not change existing product type data. All types and relations created in
                    dict will be "virtual", i.e. not visible outside of this instance of ProductTypeDict.
                    This is required when load additional dicts for comparison, filtering etc. e.g. old versions of dict
        """
        with open(json_filename, 'rb') as f:
            s = jsmin(f.read().decode("utf-8"))
        types = json.loads(s)
        if not dont_change:
            ProductType.reload()
        type_tuples = defaultdict(list)
        pseudo_sqn = 1
        seen_rel = defaultdict(dict)
        for type_str, rel_str in types.viewitems():
            type_items = type_str.split(u' + ')
            # All types are loaded from external sources or knowledge base are considered meaningful regardless of
            # other their characteristics
            pt = ProductType(*type_items, meaningful=True, singleton=not dont_change)
            wrapper = EqWrapper(pt)
            if wrapper in seen_rel:
                # Type has been added already by another relation
                pt = wrapper.match
            type_tuples[pt] = []

            # Compatibility with old format: there was one plain integer and json parse it to int() itself
            sqns_in_self, _ = re.findall('^(\d+)(?:/(\d+))?$', rel_str[0])[0] \
                                if not isinstance(rel_str[0], int) else (rel_str[0], None)
            for i in range(int(sqns_in_self)):
                type_tuples[pt].append(to_str(pseudo_sqn))
                pseudo_sqn += 1

            for r_str in rel_str[1:]:
                r_match = re.findall(u'^(\w+)(?:\[([^\]]+)\])?(~)?\s+(.*)$', r_str)
                if r_match:
                    relation, rel_attr, is_soft, type_to_str = r_match[0]
                    type_to_items = type_to_str.split(u' + ')

                    type_to = ProductType(*type_to_items, meaningful=True, singleton=not dont_change)
                    wrapper = EqWrapper(type_to)
                    if pt in seen_rel and wrapper in seen_rel[pt]:
                        # Reverse to this relation has been already created. Use type instance from it
                        type_to = wrapper.match

                    if rel_attr:
                        try:
                            rel_attr = literal_eval(rel_attr)
                        except ValueError:
                            pass  # Just use string as is
                    r_to = ProductType.Relation(from_type=pt, to_type=type_to, rel_type=relation, is_soft=is_soft == u'~', rel_attr=rel_attr)
                    if pt in seen_rel and type_to in seen_rel[pt]:
                        # Already processed back relation
                        r_from = seen_rel[pt][type_to]
                        pt.make_relation(type_to, r_to.rel_type, r_from.rel_type, r_to.is_soft, r_to.rel_attr, r_from.rel_attr)
                    else:
                        seen_rel[type_to][pt] = r_to
        self._type_tuples.clear()
        self._type_tuples.update(type_tuples)
        self._meaningful_type_tuples = None

        if self.VERBOSE:
            print("Loaded %d type tuples from json %s" % (len(self._type_tuples), json_filename))

        return self


def dump_json():
    from ok.dicts import main_options
    types = ProductTypeDict()
    ProductTypeDict.VERBOSE = True
    # types.min_meaningful_type_capacity = 2
    config = main_options(sys.argv)
    if config.products_meta_in_csvname:
        products = Product.from_meta_csv(config.products_meta_in_csvname)
        types.build_from_products(products, strict_products=True)
    else:
        types.from_json(config.product_types_in_json)
    types.to_json('out/product_types_2.json')


def update_types_in_product_meta(config):
    print("Updating types in meta products from %s" % config.products_meta_in_csvname)
    print("=" * 80)

    types = ProductTypeDict()
    types.VERBOSE = True
    print("Loading product types dict from %s" % config.product_types_in_json)
    types.from_json(config.product_types_in_json)
    types.to_json('out/product_types_1.json')
    print("Loaded %d product types" % len(types.get_type_tuples()))

    products = list(Product.from_meta_csv(config.products_meta_in_csvname))
    print('Loaded %d products from file: %s' % (len(products), config.products_meta_in_csvname))
    i_count = 0
    type_found_count = 0
    multiple_types_found_count = 0
    for p in products:
        p_all_types = types.find_product_types(p.sqn)
        type_variants = set(p_all_types)
        p_all_types2 = types.find_product_types(u'-'.join(p.sqn.split(u' ', 1)))
        type_variants.update(p_all_types2)
        p_types = type_variants
        p['types'] = p_types
        if p_types: type_found_count += 1
        if any(len(pt) > 1 for pt in p_types): multiple_types_found_count += 1
        if i_count % 100 == 0: print('.', end='')
        i_count += 1
    print()
    print("=" * 80)
    print('Found types for %d products where %d have multi-term types' % (type_found_count, multiple_types_found_count))
    products_meta_out_csvname = 'out/products_meta.csv'
    Product.to_meta_csv(products_meta_out_csvname, products)
    print('Saved results to %s' % products_meta_out_csvname)


def from_hdiet_csv(config):
    """
    Load and pre-parse products raw data from HDiet crawler
    @type prodcsvname: str
    @return:
    """
    from ok.dicts.prodproc import ProductFQNParser
    from ok.dicts import remove_nbsp

    print("Generating product types dict from hdiet+products...")
    print("=" * 80)

    types = ProductTypeDict()
    ProductTypeDict.VERBOSE = True
    types.min_meaningful_type_capacity = 1

    if not config.product_types_in_json:
        print("Loading hdiet products from %s" % config.prodcsvname)
        products = []
        with open(config.prodcsvname, "rb") as f:
            reader = csv.reader(f)
            fields = next(reader)
            parser = ProductFQNParser()
            for row in reader:
                prod_row = dict(zip(fields, row))
                item = dict(prod_row)
                pfqn = remove_nbsp(to_str(item["name"]))

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
        print("Loaded %d hdiet products from %s" % (len(products), config.prodcsvname))

        type_tuples = types.build_from_products(products, strict_products=True)
        for t in type_tuples:
            t.meaningful = True
        types.to_json('out/product_types_hdiet.json')
    else:
        print("Loading pre-processed hdiet product types from %s" % config.product_types_in_json)
        types.from_json(config.product_types_in_json)

    print("=" * 80)
    print("Loading general products from meta %s" % config.products_meta_in_csvname)
    products = Product.from_meta_csv(config.products_meta_in_csvname)
    products, len_p = itertools.tee(products)
    print("Try to merge generated types from meta: %d products" % len(list(len_p)))
    print("=" * 80)

    types.min_meaningful_type_capacity = 2
    type_tuples = types.build_from_products(products, strict_products=True)
    types.to_json('out/product_types_merged.json')

    print("=" * 80)
    print("Total types after merge: %d/%d" % (len(type_tuples), len(types.get_type_tuples(meaningful_only=True))))

    ProductType.print_stats()
    TypeTerm.term_dict.print_stats()

def print_sqn_tails():
    from ok.dicts import main_options
    config = main_options(sys.argv)
    products = Product.from_meta_csv(config.products_meta_in_csvname)
    types = ProductTypeDict()
    types.VERBOSE = True
    types.build_from_products(products)

    s = dict()
    s_type = dict()
    for t, sqns in sorted(types.get_type_tuples().viewitems(), key=lambda _t: len(_t[0])*100 + len(to_str(_t[0])), reverse=True):
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
    for sqn, tail in sorted(s.viewitems(), key=lambda _t: _t[0]):
        print(u'%s => %s, types: %s' % (sqn, tail, u' '.join(map(unicode, s_type[sqn]))))
        if tail:
            t_products.append(Product(sqn=tail))

    tails = types.collect_type_tuples(t_products)
    for t, s in sorted(tails.viewitems(), key=lambda _t: len(set(_t[1])), reverse=True):
        if len(set(s)) < 3: continue
        print(u'%s: %s' % (t, len(set(s))))


def reload_product_type_dict(config=None):
    import ok.dicts

    if not config:
        config = ok.dicts.main_options([])
    pd = ProductTypeDict()
    pd.VERBOSE = True
    pd.from_json(config.product_types_in_json)
    return pd

if __name__ == '__main__':
    import sys
    import ok.dicts
    try:
        config = ok.dicts.main_options(sys.argv)
        # print_sqn_tails()
        if config.action == 'dump-json':
            dump_json()
        elif config.action == 'update-products':
            update_types_in_product_meta(config)
        elif config.action == 'gen-types-hdiet-products':
            # Set defaults
            config = ok.dicts.main_options(sys.argv, prodcsvname='product_types_raw_hdiet.csv',
                                           product_types_in_json=None)
            from_hdiet_csv(config)
    except Exception as e:
        print()
        print("Exception caught: %s" % e.message)
        raise
