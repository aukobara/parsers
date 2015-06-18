# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
from collections import namedtuple
from ok.dicts import to_str

from ok.dicts.term import TypeTerm, TermContext

# identical relation is special relation type that is used in runtime type matching only and is not present in regular
# types dict. It is used to distinguish really the same types and types are 'same-same' i.e. equals (comparing their
# main forms and ignoring terms order)
TYPE_TUPLE_RELATION_IDENTICAL = u"identical"
TYPE_TUPLE_RELATION_EQUALS = u"equals"
TYPE_TUPLE_RELATION_SIMILAR = u"similar"
TYPE_TUPLE_RELATION_ALMOST = u"almost"
TYPE_TUPLE_RELATION_CONTAINS = u"contains"
TYPE_TUPLE_RELATION_SUBSET_OF = u"subset_of"
TYPE_TUPLE_RELATION_SUPPORTED_TYPES = [TYPE_TUPLE_RELATION_IDENTICAL, TYPE_TUPLE_RELATION_EQUALS,
                                       TYPE_TUPLE_RELATION_SIMILAR, TYPE_TUPLE_RELATION_ALMOST,
                                       TYPE_TUPLE_RELATION_CONTAINS, TYPE_TUPLE_RELATION_SUBSET_OF]

class ProductType(tuple):
    class Relation(namedtuple('Relation', 'from_type to_type rel_type is_soft rel_attr')):

        def __new__(cls, *args, **kwargs):
            self = super(ProductType.Relation, cls).__new__(cls, *args, **kwargs)
            self._back_relation = None
            return self

        def __unicode__(self):
            return u'%s%s%s %s' % (
                self.rel_type, u'[%s]' % to_str(self.rel_attr) if self.rel_attr else '', u'~' if self.is_soft else '',
                self.to_type)

        def __str__(self):
            return self.__unicode__().encode("utf-8")

        @property
        def back_relation(self):
            return self._back_relation

    __slot__ = ('_relations, __relations_cache', '_meaningful', '__same_same_hash_cache', '_singleton')

    # ProductType instances acts as singleton. All instances are kept here
    __v = set()
    """@type: set[ProductType]"""

    def __new__(cls, *args, **kwargs):
        self = tuple.__new__(cls, (TypeTerm.make(term).term_id for term in args))
        """@type: ProductType"""
        self._singleton = False

        if not kwargs.get('_skip_cache_lookup', False) and kwargs.get('singleton', True):
            wrapper = EqWrapper(self)
            if wrapper in cls.__v:
                self = wrapper.match
                assert self._singleton

        return self

    def __init__(self, *args, **kwargs):
        if not self.singleton:
            self._relations = dict()
            self.__relations_cache = None
            """ @type: dict of (ProductType, ProductType.Relation) """
            self.__same_same_hash_cache = None

            self._meaningful = kwargs.get('meaningful', False)
            singleton = kwargs.get('singleton', True)
            assert all(k in ('singleton', 'meaningful', '_skip_cache_lookup') for k in kwargs), \
                'Unknown ProductType option: %s' % ', '.join(kwargs.keys())

            # tuple.__init__(self, args)
            self.term_context = TermContext(self)

            self._singleton = singleton
            if self._singleton:
                self.__v.add(self)

    @property
    def singleton(self):
        return self._singleton

    @classmethod
    def make_from_terms(cls, terms, meaningful=False):
        """@param list[TypeTerm] terms: list of TypeTerms"""
        wrapper = EqWrapper(terms)
        if wrapper in cls.__v:
            found = wrapper.match
            assert found._singleton
        else:
            found = ProductType(*terms, meaningful=meaningful, _skip_cache_lookup=True)
        return found

    def __getitem__(self, y):
        term_id = super(ProductType, self).__getitem__(y)
        return TypeTerm.get_by_id(term_id)

    def __iter__(self):
        return (TypeTerm.get_by_id(term_id) for term_id in super(ProductType, self).__iter__())

    def __getslice__(self, i, j):
        return [TypeTerm.get_by_id(term_id) for term_id in super(ProductType, self).__getslice__(i, j)]

    @staticmethod
    def all_cached_singletons():
        """@rtype: list[ProductType]"""
        return sorted(ProductType.__v, key=to_str)

    @staticmethod
    def reload():
        """
        Clear all type tuple singletons
        """
        ProductType.__v.clear()

    @staticmethod
    def print_stats():
        print('ProductType set stats:\r\n\tsingleton cache: %d' % len(ProductType.all_cached_singletons()))

    def make_relation(self, p_type2, rel_from, rel_to, is_soft=False, rel_attr_from=None, rel_attr_to=None,
                      dont_change=False, one_way=False):
        """
        Add relation to both self and specified ProductType
        @param ProductType p_type2: another type
        @param unicode rel_from: from self to second
        @param unicode rel_from: from second to first
        @param bool is_soft: relation will not conflict ever - just for mark, not constraint.
                        It is always can be overwritten by hard relation. But soft relation will never overwrite hard
        @param unicode rel_attr_from: Relation may have own attribute (like weight). None, by default
        @param unicode rel_attr_to: The same for back relation
        @param bool dont_change: if True only do validation and return new Relation instance.
                        Do not change ProductType instance. It can be applied later with copy_relation() method
        @param bool one_way: if True do not create back relation
        @return:
        """
        assert type(dont_change) == bool and type(one_way) == bool and type(is_soft) == bool
        assert rel_from in TYPE_TUPLE_RELATION_SUPPORTED_TYPES and rel_to in TYPE_TUPLE_RELATION_SUPPORTED_TYPES

        relation = self._relations.get(p_type2)
        if relation and relation.rel_type != rel_from and not(relation.is_soft or is_soft):
            e = Exception(u"ProductType%s has conflicting relations already with %s" % (self, p_type2))
            print(to_str(e))
            raise e
        if not relation or (relation.is_soft and not is_soft):
            relation = self.Relation(self, p_type2, rel_from, is_soft=is_soft, rel_attr=rel_attr_from)
            if not dont_change:
                self._relations[p_type2] = relation
                self.__relations_cache = None
            if not one_way:
                # Notify second party about relation. It should not create back relation to avoid recursion
                back_relation = p_type2.make_relation(self, rel_to, rel_from, is_soft=is_soft,
                                      rel_attr_from=rel_attr_to, rel_attr_to=rel_attr_from,
                                      dont_change=dont_change, one_way=True)
                relation._back_relation = back_relation
                back_relation._back_relation = relation
        return relation

    def copy_relation(self, relation_copy):
        """
        @param ProductType.Relation relation_copy: from relation
        @return:
        """
        back_relation_copy = relation_copy.back_relation
        return self.make_relation(relation_copy.to_type, relation_copy.rel_type, back_relation_copy.rel_type,
                                  is_soft=relation_copy.is_soft,
                                  rel_attr_from=relation_copy.rel_attr, rel_attr_to=back_relation_copy.rel_attr)

    def identical(self, p_type2, dont_change=False):
        """
        This is a special relation type to link two copies of the same product type. It should never happen in
        dict types where type singletons are used
        """
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_IDENTICAL, TYPE_TUPLE_RELATION_IDENTICAL, dont_change=dont_change)

    def equals_to(self, p_type2, dont_change=False):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_EQUALS, TYPE_TUPLE_RELATION_EQUALS, dont_change=dont_change)

    def similar(self, p_type2, similarity, dont_change=False):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_SIMILAR, TYPE_TUPLE_RELATION_SIMILAR, is_soft=True,
                                  rel_attr_from=similarity, rel_attr_to=similarity, dont_change=dont_change)

    def almost(self, p_type2, similarity_from, similarity_to, dont_change=False):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_ALMOST, TYPE_TUPLE_RELATION_ALMOST, is_soft=True,
                                  rel_attr_from=similarity_from, rel_attr_to=similarity_to, dont_change=dont_change)

    def contains(self, p_type2, dont_change=False):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_CONTAINS, TYPE_TUPLE_RELATION_SUBSET_OF, dont_change=dont_change)

    def subset_of(self, p_type2, dont_change=False):
        return self.make_relation(p_type2, TYPE_TUPLE_RELATION_SUBSET_OF, TYPE_TUPLE_RELATION_CONTAINS, dont_change=dont_change)

    def not_related(self, p_type2):
        relation = self.get_relation(p_type2)
        if relation:
            del self._relations[p_type2]
            self.__relations_cache = None
            p_type2.not_related(self)

    def get_relation(self, r_type2):
        return self._relations.get(r_type2)

    def relations(self, *rel_type):
        """
        @param list[unicode] rel_type: Relation type list. If empty - all return
        @rtype: list[ProductType.Relation]
        """
        if self.__relations_cache is None or rel_type not in self.__relations_cache:
            self.__relations_cache = self.__relations_cache or dict()
            self.__relations_cache[rel_type] = sorted([rel for rel in self._relations.values()
                                                      if not rel_type or rel.rel_type in rel_type],
                                                      key=self.relation_sort_key)
        return self.__relations_cache[rel_type]

    @staticmethod
    def relation_sort_key(relation):
        attr_key = ''
        if relation.rel_type in (TYPE_TUPLE_RELATION_SIMILAR, TYPE_TUPLE_RELATION_ALMOST):
            rel_attr = 1 - float(relation.rel_attr or '0')
            attr_key = '%0.2f' % rel_attr
        key = u'%s|%s|%s' % (relation.rel_type, attr_key, to_str(relation.to_type))
        return key

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

    @property
    def meaningful(self):
        return self._meaningful

    @meaningful.setter
    def meaningful(self, meaningful):
        self._meaningful = meaningful

    def as_string(self, delimiter=u' '):
        return delimiter.join(term.as_string() for term in self)

    def __unicode__(self):
        return u' + '.join(self)

    def __str__(self):
        return self.__unicode__().encode("utf-8")

    def __repr__(self):
        return b' + '.join(repr(term) for term in iter(self))

    def get_terms_ids(self):
        return tuple(super(ProductType, self).__iter__())

    def get_main_form_term_ids(self):
        return [TypeTerm.get_by_id(term_id).get_main_form(context=self.term_context).term_id
                for term_id in self.get_terms_ids()]

    @staticmethod
    def calculate_same_same_hash(terms):
        """
        Return hash sustainable to terms order and word forms.
        If term has word forms take minimum term number of all forms.
        This will group all types produced from same-same words combinations.
        @param tuple[int|unicode|TypeTerm] terms: term set
        @return: int hashcode that equals for all unordered term sets with same word forms
        @rtype: int
        """
        type_terms = []
        for term_item in terms:
            term = TypeTerm.get_by_id(term_item) if isinstance(term_item, int) else TypeTerm.make(term_item)
            """@type: TypeTerm"""
            if term is None:
                raise Exception("No such term in dict with term_id: %d" % term_item)
            type_terms.append(term)
        term_context = TermContext.ensure_context(type_terms)
        hash_terms = [term.get_main_form(context=term_context).term_id for term in type_terms]
        return frozenset(hash_terms).__hash__()

    def get_same_same_hash(self):
        """
        Hash value is cached due to immutable nature of Terms and ProductType term set
        @return: int
        """
        if self.__same_same_hash_cache is None:
            self.__same_same_hash_cache = self.calculate_same_same_hash(self.get_terms_ids())
        return self.__same_same_hash_cache


class EqWrapper(ProductType):
    def __new__(cls, *args):
        self = tuple.__new__(cls, [id.term_id if isinstance(id, TypeTerm) else id for id in args[0]])
        self.obj = args[0] if isinstance(args[0], ProductType) else self.get_terms_ids()
        self.match = None
        self._singleton = True
        return self

    def __eq__(self, other):
        result = (self.obj == other)
        if result:
            self.match = other
        return result

    def __getattr__(self, item):
        return getattr(self.obj, item)
