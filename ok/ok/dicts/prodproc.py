# -*- coding: utf-8 -*-

import csv
from itertools import combinations
import re
import json
from sys import argv

from ok.items import ProductItem
from ok.dicts import cleanup_token_str, remove_nbsp, main_options
from ok.dicts.brand import Brand
from ok.dicts.catsproc import Cats

TYPE_TUPLE_RELATION_EQUALS = u"equals"
TYPE_TUPLE_RELATION_CONTAINS = u"contains"
TYPE_TUPLE_RELATION_SUBSET_OF = u"subset_of"
TYPE_TUPLE_MIN_CAPACITY = 4  # Number of SQNs covered by word combination

ATTRIBUTE_BRAND = u"Бренд:"
ATTRIBUTE_MANUFACTURER = u"Изготовитель:"
ATTRIBUTE_WEIGHT = u"Вес:"

# prefix can be consumed by re parser and must be returned in sub - must be always 1st Match
RE_TEMPLATE_PFQN_PRE = u'(?:\s|\.|,|\()'
# post is predicate and isn't consumed by parser. but must start immediately after term group
RE_TEMPLATE_PFQN_POST = u'(?=\s|$|,|\.|\)|/)'

RE_TEMPLATE_PFQN_WEIGHT_FULL = u'(\D)(' +\
                u'(?:фасовка\s+)?(?:\d+(?:шт|пак)?\s*(?:х|\*|x|/))?\s*' +\
                u'(?:\d+(?:[\.,]\d+)?\s*)' +\
                u'(?:кг|г|л|мл|гр)\.?' +\
                u'(?:(?:х|\*|x|/)\d+(?:\s*шт)?)?' +\
                u')' + RE_TEMPLATE_PFQN_POST
RE_TEMPLATE_PFQN_WEIGHT_SHORT = u'(\D' + RE_TEMPLATE_PFQN_PRE + u')((?:кг|г|л|мл|гр)\.?)' + RE_TEMPLATE_PFQN_POST

RE_TEMPLATE_PFQN_FAT_MDZH = u'(?:\s*(?:с\s)?м\.?д\.?ж\.? в сух(?:ом)?\.?\s?вещ(?:-|ест)ве\s*' + \
                            u'|\s*массовая доля жира в сухом веществе\s*)?'
RE_TEMPLATE_PFQN_FAT = u'(' + RE_TEMPLATE_PFQN_PRE + u')(' + RE_TEMPLATE_PFQN_FAT_MDZH + \
                       u'(?:\d+(?:[\.,]\d+)?%?-)?\d+(?:[\.,]\d+)?\s*%(?:\s*жирн(?:\.|ости)?)?' + \
                       RE_TEMPLATE_PFQN_FAT_MDZH + u")" + RE_TEMPLATE_PFQN_POST

RE_TEMPLATE_PFQN_PACK = u'(' + RE_TEMPLATE_PFQN_PRE + u')' \
                        u'(т/пак|ж/б|ст/б|м/у|с/б|ст\\\б|ст/бут|бут|пл/б|пл/бут|пэтбутылка|пл|кор\.?|коробка' + \
                        u'|\d*\s*пак\.?|\d+\s*таб|\d+\s*саше|\d+\s*пир(?:\.|амидок)?' + \
                        u'|(?:\d+\s*)?шт\.?|упак\.?|уп\.?|в/у|п/э|жесть|круг|обрам' + \
                        u'|вакуум|нарезка|нар|стакан|ванночка|в\sванночке|дой-пак|дой/пак|пюр-пак|пюр\sпак' + \
                        u'|зип|зип-пакет|д/пак|п/пак|пл\.упаковка|пэт|пакет|туба|ведро|бан|лоток|фольга' + \
                        u'|фас(?:ованные)?|н/подл\.?|ф/пакет|0[.,]5|0[.,]75|0[.,]33)' + RE_TEMPLATE_PFQN_POST


class ProductType(tuple):

    def __new__(cls, *args, **kwargs):
        return tuple.__new__(cls, args)


class Product(dict):

    @property
    def pfqn(self):
        """
        @rtype: unicode
        """
        return self["pfqn"]

    @pfqn.setter
    def pfqn(self, pfqn):
        self["pfqn"] = pfqn

    @property
    def sqn(self):
        """
        @rtype: unicode
        """
        return self["sqn"]

    @sqn.setter
    def sqn(self, sqn):
        self["sqn"] = sqn


class ProductFQNParser(object):

    __pfqn_re_weight_full = re.compile(RE_TEMPLATE_PFQN_WEIGHT_FULL, re.IGNORECASE | re.UNICODE)
    __pfqn_re_weight_short = re.compile(RE_TEMPLATE_PFQN_WEIGHT_SHORT, re.IGNORECASE | re.UNICODE)
    __pfqn_re_fat = re.compile(RE_TEMPLATE_PFQN_FAT, re.IGNORECASE | re.UNICODE)
    __pfqn_re_pack = re.compile(RE_TEMPLATE_PFQN_PACK, re.IGNORECASE | re.UNICODE)

    def __init__(self):
        self.types = dict()
        """ @type types: dict of (unicode, Product) """
        self.weights = dict()
        self.fats = dict()
        self.packs = dict()

        self.ignore_category_id_list = None
        self.accept_category_id_list = None
        self.cats = Cats()
        self.root_types = set()

    def use_cats_from_csv(self, cat_csvname):
        self.cats.from_csv(cat_csvname)

    def ignore_cats(self, *ignore_cat_names):
        for cat_name in ignore_cat_names:
            cat_id = self.cats.find_by_title(cat_name)
            if cat_id:
                self.ignore_category_id_list = self.ignore_category_id_list or []
                self.ignore_category_id_list.append(cat_id)

    def accept_cats(self, *accept_cat_names):
        """
        Only accept products under specified cats. If not specified accept all except under ignore_cats, if specified.
        NOTE: If both accept_cats and ignore_cats are specified logic may be complicated for products under multiple
        cats. E.g. even if product is accepted it can be ignored if it is under one of ignore cats.
        @param accept_cat_names:
        @return:
        """
        for cat_name in accept_cat_names:
            cat_id = self.cats.find_by_title(cat_name)
            if cat_id:
                self.accept_category_id_list = self.accept_category_id_list or []
                self.accept_category_id_list.append(cat_id)


    @staticmethod
    def parse_pfqn(pfqn):
        """
        Parse Full Product Name and return name parts: weight, fat, pack and SQN
        SQN is shorten product type name without above attributes and with normilized spaces and non word symbols
        If some attributes have multiple values - return concatenated string with " + " delimiter
        (see @cleanup_token_str)
        @param unicode pfqn: Full Product Name
        @rtype: (unicode, unicode, unicode, unicode)
        """
        sqn = pfqn.lower()

        def _add_match(ll, match):
            _pre = match.group(1)
            _m = match.group(2)
            ll[0] = (ll[0] + u" + " if ll[0] else "") + _m.strip()
            return _pre

        # weight - if has digit should be bounded by non-Digit, if has no digit - than unit only is acceptable but as token
        wl = [u""]
        sqn = re.sub(ProductFQNParser.__pfqn_re_weight_full, lambda g: _add_match(wl, g), sqn)
        if not wl[0]:
            sqn = re.sub(ProductFQNParser.__pfqn_re_weight_short, lambda g: _add_match(wl, g), sqn )
        # fat
        fl=[u""]
        sqn = re.sub(ProductFQNParser.__pfqn_re_fat, lambda g: _add_match(fl, g), sqn )
        # pack
        pl=[u""]
        sqn = re.sub(ProductFQNParser.__pfqn_re_pack, lambda g: _add_match(pl, g), sqn )

        return wl[0], fl[0], pl[0], cleanup_token_str(sqn)

    def extract_product(self, pfqn, brand=None, manufacturer_brand=None, product_cls=Product):
        """
        Parse PFQN and build new instance of Product. If brand is specified and non UNKNOWN - replace brand in PFQN
        As side effects - count weight, fat, pack constants in internal storage.
        Save reference to new Product in types
        @param unicode pfqn: PFQN
        @param Brand|None brand: known brand
        @param Brand|None manufacturer_brand: known manufacturer
        @param product_cls: class of new Product instance. By default, Product. It can be any dict subclass
        @rtype: Product|dict
        """
        (weight, fat, pack, sqn) = self.parse_pfqn(pfqn)

        def __fill_fqn_dict(d, item):
            for k in item.split(u" + "): d[k] = d.get(k, 0) + 1

        __fill_fqn_dict(self.weights, weight)
        __fill_fqn_dict(self.fats, fat)
        __fill_fqn_dict(self.packs, pack)

        sqn_without_brand = sqn
        if brand and brand.name != Brand.UNKNOWN_BRAND_NAME:
            sqn_without_brand = brand.replace_brand(sqn_without_brand)

        product = product_cls(pfqn=pfqn, weight=weight, fat=fat, pack=pack,
                              brand=brand.name if brand else Brand.UNKNOWN_BRAND_NAME,
                              sqn=sqn_without_brand, brand_detected=sqn != sqn_without_brand,
                              product_manufacturer=manufacturer_brand.name if manufacturer_brand else None)
        self.types[pfqn] = product  # TODO: Check if types already contain specified PFQN
        return product

    def from_csv(self, prodcsvname):
        with open(prodcsvname, "rb") as f:
            reader = csv.reader(f)
            fields = next(reader)
            for row in reader:
                prodrow = dict(zip(fields, row))
                item = ProductItem(prodrow)
                pfqn = remove_nbsp(unicode(item["name"], "utf-8"))

                if self.accept_category_id_list and not any(self.cats.is_product_under(item["id"], cat_id) for cat_id in self.accept_category_id_list if cat_id):
                    # If accept cat list defined - only accept products under specified cats.
                    # if list undefined - accept all
                    continue

                if self.ignore_category_id_list and any(self.cats.is_product_under(item["id"], cat_id) for cat_id in self.ignore_category_id_list if cat_id):
                    # If ignore cat list defined - ignore products under specified cats
                    continue

                manufacturer_brand = None
                if item.get("details"):
                    details = json.loads(item["details"])
                    """ @type details: dict of (unicode, unicode) """

                    brand = Brand.findOrCreate(remove_nbsp(details.get(ATTRIBUTE_BRAND, Brand.UNKNOWN_BRAND_NAME)))

                    product_manufacturer = remove_nbsp(details.get(ATTRIBUTE_MANUFACTURER))
                    if product_manufacturer:
                        brand.manufacturers.add(product_manufacturer)
                        manufacturer_brand = Brand.findOrCreate_manufacturer_brand(product_manufacturer)
                        if not brand.no_brand and brand != manufacturer_brand:
                            manufacturer_brand.link_related(brand)
                else:
                    brand = Brand.findOrCreate(Brand.UNKNOWN_BRAND_NAME)

                self.extract_product(pfqn, brand, manufacturer_brand)

    def process_manufacturers_as_brands(self):
        """
        Process manufacturers as brands
        @return tuples of sqn like (before_replacement, after_replacement)
        @rtype: list[tuple(unicode,unicode)]
        """
        manufacturer_replacements = []
        for product in self.types.itervalues():
            # Here process manufacturers only where present.
            if not product["product_manufacturer"]:
                # TODO: Try to link the same manufacturer names with different spelling by brand name
                continue

            product_manufacturer = product["product_manufacturer"]
            brand = Brand.exist(product["brand"])

            sqn_without_brand = product.sqn
            sqn_last_change = sqn_without_brand
            linked_manufacturers = {product_manufacturer}  # TODO: Try other brands of the same or related manufacturers
            for manufacturer in linked_manufacturers:
                manufacturer_brand = Brand.findOrCreate_manufacturer_brand(manufacturer)
                if manufacturer_brand and manufacturer_brand != brand:
                    # Consider manufacturer as brand - replace its synonyms
                    sqn_without_brand = manufacturer_brand.replace_brand(sqn_without_brand)
                    if sqn_last_change != sqn_without_brand:
                        product.sqn = sqn_without_brand
                        product["brand_detected"] = True
                        manufacturer_replacements.append((sqn_last_change, sqn_without_brand))
                        sqn_last_change = sqn_without_brand
        return manufacturer_replacements

    def guess_no_brand_manufacturers(self):
        """
        Here try to guess about no-brand products w/o manufacturers.
        Iterate through all known no-brand manufacturers and try to apply them and check what happens
        Later it will be possible to extend for all products
        @return tuples of sqn like (before_replacement, after_replacement)
        @rtype: list[tuple(unicode,unicode)]
        """
        no_brand_replacements = []
        no_brand_manufacturers = {m for b_name in Brand.no_brand_names() for m in Brand.findOrCreate(b_name).manufacturers}
        for product in self.types.itervalues():
            if product["product_manufacturer"] or product["brand"] not in Brand.no_brand_names():
                continue

            sqn_without_brand = product.sqn
            sqn_last_change = sqn_without_brand
            for manufacturer in no_brand_manufacturers:
                manufacturer_brand = Brand.findOrCreate_manufacturer_brand(manufacturer)
                # Consider manufacturer as brand - replace its synonyms
                sqn_without_brand = manufacturer_brand.replace_brand(sqn_without_brand, add_new_synonyms=False)
                if sqn_last_change != sqn_without_brand:
                    product.sqn = sqn_without_brand
                    product["brand_detected"] = True
                    no_brand_replacements.append((sqn_last_change, sqn_without_brand))
                    sqn_last_change = sqn_without_brand
        return no_brand_replacements

    @staticmethod
    def guess_one_sqn(sqn):
        result = []
        for brand in Brand.all(skip_no_brand=True):
            sqn_without_brand = brand.replace_brand(sqn, add_new_synonyms=False)
            if sqn != sqn_without_brand:
                result.append((brand.name, sqn_without_brand))
        return result

    def guess_unknown_brands(self):
        """
        Here try to guess about products where brand has not been detected after scan of brand and manufacturer.
        This method will not change anything but print it's hypothesis that can be accepted manually
        @return tuples of sqn like (before_replacement, after_replacement)
        @rtype: list[tuple(unicode,unicode)]
        """
        for product in self.types.itervalues():
            if product["brand_detected"]:
                continue

            guesses = self.guess_one_sqn(product)
            for guess in guesses:
                print u"Brand [%s] may be in product type [sqn:%s, brand: %s, manufacturer: %s]" % \
                      (guess[0] + u'|' + u'|'.join(Brand.exist(guess[0]).get_synonyms()),
                       product.sqn, product["brand"], product["product_manufacturer"])

    def get_sqn_set(self):
        return set(p.sqn for p in self.types.values())

    def collect_type_tuples(self):
        """
        Return dict with tuples for combinations of tokens in each parsed sqn. List of source sqns will be as value.
        Join propositions to next word to treat them as single token
        If multiple parsed products with identical sqns are present all them will be in the value list as duplicates.
        It is required to estimate "capacity" of tuple
        @rtype: dict of (ProductType, list[unicode])
        """
        result = dict()

        def add_tuple(t, p_id):
            result[t] = result.get(t, [])
            result[t].append(p_id)

        for t, d in sorted(self.types.iteritems(), key=lambda t: t[1]["sqn"].split(" ", 1)[0]):
            words = re.split(u'\s+', d["sqn"])
            words1 = []
            buf = u''
            for w in words:
                if w:
                    if w in [u'в', u'с', u'со', u'из', u'для', u'и', u'на', u'без', u'к', u'не', u'де']:
                        buf = w  # join proposition to the next word
                        continue
                    if buf:
                        # Add both word variants with proposition and w/o.
                        # Proposition is added itself as well
                        words1.append(buf + u' ' + w)
                        # words1.append(buf)
                    words1.append(w)
                    buf = u''
            if buf: words1.append(buf)

            first_word = words1.pop(0)
            add_tuple(ProductType(first_word, u''), d.sqn)
            if words1:
                for w in words1:
                    add_tuple(ProductType(first_word, w), d.sqn)
                for w1, w2 in combinations(words1, 2):
                    if w1 + u' ' in w2 or u' ' + w1 in w2 or\
                       w2 + u' ' in w1 or u' ' + w2 in w1:
                        # Do not join same world and form with proposition
                        continue
                    add_tuple(ProductType(first_word, u'%s %s' % (w1, w2)), d.sqn)
                    add_tuple(ProductType(u'%s %s' % (first_word, w1), w2), d.sqn)
        return result

    @staticmethod
    def calculate_type_tuples_relationship(type_tuples, verbose=False):
        """
        Calculate all non-repeatable combinations of type tuples with capacity not less than MIN_TUPLE_CAPACITY
        and check if one tuple is equals or contains (in terms of sqn set) another.
        @param dict of (tuple of (unicode,unicode), list[unicode]) type_tuples: from collect_type_tuples()
        @param bool verbose: type progress if specified - useful for testing of low capacity huge combinations
        @return: dict of tuples -> list of relationships in text format
        @rtype: tuple of (dict of (ProductType, list[unicode]), set[ProductType])
        """
        result = dict()
        root_types = set()

        def add_result(type1, rel1, type2, rel2):
            result[type1] = result.get(type1, [])
            result[type2] = result.get(type2, [])
            result[type1].append(u'%s %s + %s' % (rel1, type2[0], type2[1]))
            result[type2].append(u'%s %s + %s' % (rel2, type1[0], type1[1]))
            type1_already_subset = any(TYPE_TUPLE_RELATION_SUBSET_OF in rel for rel in result[type1])
            type2_already_subset = any(TYPE_TUPLE_RELATION_SUBSET_OF in rel for rel in result[type2])
            if rel1 == TYPE_TUPLE_RELATION_CONTAINS:
                if type2 in root_types:
                    root_types.remove(type2)
                if not type1_already_subset:
                    root_types.add(type1)
            elif rel2 == TYPE_TUPLE_RELATION_CONTAINS:
                if type1 in root_types:
                    root_types.remove(type1)
                if not type2_already_subset:
                    root_types.add(type2)

        i_count = 0
        for t1, t2 in combinations([it for it in type_tuples.iteritems() if len(it[1]) >= TYPE_TUPLE_MIN_CAPACITY], 2):
            s1 = set(t1[1])
            s2 = set(t2[1])
            if s1.issubset(s2):
                if len(s1) < len(s2):
                    add_result(t1[0], TYPE_TUPLE_RELATION_SUBSET_OF, t2[0], TYPE_TUPLE_RELATION_CONTAINS)
                else:
                    add_result(t1[0], TYPE_TUPLE_RELATION_EQUALS, t2[0], TYPE_TUPLE_RELATION_EQUALS)
            elif s2.issubset(s1):
                add_result(t1[0], TYPE_TUPLE_RELATION_CONTAINS, t2[0], TYPE_TUPLE_RELATION_SUBSET_OF)
            i_count += 1
            if verbose and i_count % 10000 == 0: print u'.',
            if verbose and i_count % 1000000 == 0: print i_count
        if verbose: print

        for t in type_tuples:
            if not any(TYPE_TUPLE_RELATION_SUBSET_OF in rel or TYPE_TUPLE_RELATION_CONTAINS in rel for rel in result.get(t, [])):
                root_types.add(t)

        return result, root_types

    def get_type_tuples(self, verbose=False):
        """
        @return dict of ProductTypes, ProductType's relations and set of root ProductTypes
        @rtype: tuple of (dict of (ProductType, list[unicode]), dict of (ProductType, list[unicode]), set[ProductType])
        """
        # TODO Cache everything here until self.types is changed
        type_tuples = self.collect_type_tuples()
        (type_tuples_rel, root_types) = self.calculate_type_tuples_relationship(type_tuples, verbose)
        return type_tuples, type_tuples_rel, root_types


def main_parse_products(prodcsvname, cat_csvname=None, brands_in_csvname=None, brands_out_csvname=None, **kwargs):
    pfqnParser = ProductFQNParser()
    if cat_csvname:
        pfqnParser.use_cats_from_csv(cat_csvname)
        print "Categories've been loaded from '%s': %d" % (cat_csvname, len(pfqnParser.cats))
    accept_cat_names = set(c.lower() for c in pfqnParser.cats.get_root_cats())
    accept_cat_names -= {u"Алкогольные напитки".lower(), u"Скидки".lower()}
    pfqnParser.accept_cats(*accept_cat_names)
    if brands_in_csvname:
        (total, new_brands) = Brand.from_csv(brands_in_csvname)
        print "Brands and manufacturers 've been loaded from '%s': %d (of %d)" % (brands_in_csvname, new_brands, total)
    print
    print "================== Parse products - marketing brands part - from '%s' =====================" % prodcsvname
    pfqnParser.from_csv(prodcsvname)
    print
    print "============== Parse products - manufacturers brands part - from '%s' =================" % prodcsvname
    pfqnParser.process_manufacturers_as_brands()
    enabled_brand_guesses = True
    if enabled_brand_guesses:
        print
        print "============== Try guess about manufactures of no-brand products from '%s' ===============" % prodcsvname
        no_brand_replacements = pfqnParser.guess_no_brand_manufacturers()
        for repl in no_brand_replacements:
            print "NO BRAND REPLACEMENT: OLD: %s, NEW: %s" % repl
        print "NO BRAND GUESS REPLACEMENTS: %d" % len(no_brand_replacements)

    # pfqnParser.guess_unknown_brands()
    # ########### SAVE RESULTS ####################
    if brands_out_csvname:
        with open(brands_out_csvname, 'wb') as f:
            f.truncate()
            Brand.to_csv(f)
        print "Stored %d brands to csv[%s]" % (len(Brand.all()), brands_out_csvname)

    return pfqnParser


def print_brands():
    manufacturers = dict()
    """ @type manufacturers: dict of (unicode, list[unicode]) """
    for b in Brand.all():
        # print b
        for m in set(im.strip().lower() for im in b.manufacturers):
            m_brand = Brand.findOrCreate_manufacturer_brand(m)
            manufacturers[m_brand.name] = manufacturers.get(m_brand.name, [])
            manufacturers[m_brand.name].append(b.name)
            manufacturers[m_brand.name] += map(lambda s: "~" + s, b.get_synonyms(copy_related=False))
    print "Total brands: %d" % len(Brand.all())
    print
    for m, b in sorted(manufacturers.iteritems(), key=lambda t: t[0]):
        print "%s [%s]" % (m, "|".join(b))
        for (linked_m, linked_b) in [(im.name, ib) for ib in b if Brand.exist(ib)
                                     for im in
                                     set(map(Brand.findOrCreate_manufacturer_brand, Brand.exist(ib).manufacturers))
                                     if im.name != m and ib not in Brand.no_brand_names() and
                                             (ib != u"О'КЕЙ" or m == u"ООО \"О'КЕЙ\"")]:
            print "    =%s=> %s [%s]" % (linked_b, linked_m, "|".join(manufacturers[linked_m]))
    print "Total manufacturers: %d" % len(manufacturers)


def print_product_types(pfqn_parser):
    ptypes_count = 0
    nobrand_count = 0
    m_count = dict()
    # for t, d in sorted(types.iteritems(), key=lambda t: t[1]["sqn"].split(" ", 1)[0]):
    for t, d in sorted(pfqn_parser.types.iteritems(), key=lambda t: t[1]["product_manufacturer"]):
        if not d["brand_detected"] and (d["brand"] in Brand.no_brand_names()):
            # print '%s   => brand: %s, prod_man: %s, weight: %s, fat: %s, pack: %s, fqn: %s' % \
            # (d["sqn"], d["brand"], d["product_manufacturer"], d["weight"], d["fat"], d["pack"], t)
            nobrand_count += 1

        elif not d["brand_detected"]:
            print '%s   => brand: %s, prod_man: %s, weight: %s, fat: %s, pack: %s, fqn: %s' % \
                  (d["sqn"], d["brand"], d["product_manufacturer"], d["weight"], d["fat"], d["pack"], t)
            m_count[d["brand"]] = m_count.get(d["brand"], 0)
            m_count[d["brand"]] += 1
            ptypes_count += 1
    print
    print "Total product types: %d [notintype: %d, nobrand: %d]" % (len(pfqn_parser.types), ptypes_count, nobrand_count)
    print
    for m, c in sorted(m_count.iteritems(), key=lambda t: t[1], reverse=True):
        print "%d : %s" % (c, m)


def print_type_tuples(pfqn_parser):
    """
    @param ProductFQNParser pfqn_parser: parser
    """
    sqn_all_set = pfqn_parser.get_sqn_set()
    (type_tuples, type_tuples_rel, root_types) = pfqn_parser.get_type_tuples(verbose=True)

    num_tuples = dict()
    sqn_selected_set = set()

    def print_type_descendant_tuples(desc_type_tuples, indent=u''):
        for t in sorted(desc_type_tuples, key=lambda k: u' '.join(k[0]).replace(u'+', u'')):
            p_ids = type_tuples[t]
            c = len(p_ids)
            if c < TYPE_TUPLE_MIN_CAPACITY: continue
            print "%sTuple[%s] %s + %s: %d" % (indent, 'ROOT' if t in root_types else '', t[0], t[1], c),
            num_tuples[c] = num_tuples.get(c, 0) + 1
            sqn_selected_set.update(p_ids)

            child_types = []
            """@type: list[ProductType] """
            if t in type_tuples_rel:
                print u' *** ',
                is_first_rel = True
                for rel in type_tuples_rel[t]:
                    if TYPE_TUPLE_RELATION_EQUALS in rel:
                        # Print equals relations only, because other are in structure
                        if not is_first_rel: print u', ',
                        print rel,
                    is_first_rel = False
                    contains = re.findall(TYPE_TUPLE_RELATION_CONTAINS + u'\s+(.*)\s+\+\s+(.*)\s*', rel)
                    if contains:
                        child_types.append(ProductType(*contains[0]))
            print

            if child_types:
                immediate_child_types = []
                for child in child_types:
                    # Do not recurse grand-children
                    child_ancestors = [re.findall(TYPE_TUPLE_RELATION_SUBSET_OF + u'\s+(.*)\s+\+\s+(.*)\s*', rel)
                                       for rel in type_tuples_rel[child]]
                    if not any(anc and anc[0] in child_types for anc in child_ancestors):
                        # For equal types recurse only one, i.e. ignore if equals has been added already
                        child_equals = [re.findall(TYPE_TUPLE_RELATION_EQUALS + u'\s+(.*)\s+\+\s+(.*)\s*', rel)
                                           for rel in type_tuples_rel[child]]
                        if not any(eqls and eqls[0] in immediate_child_types for eqls in child_equals):
                            immediate_child_types.append(child)

                print_type_descendant_tuples(immediate_child_types, indent + u'    ')

    print_type_descendant_tuples(root_types)

    print "Total tuples: selected %d of %d total" % (sum(num_tuples.values()), len(type_tuples))
    print "Total SQN: %d (%d%%) of %d total" % (
        len(sqn_selected_set), 100.0 * len(sqn_selected_set) / len(sqn_all_set), len(sqn_all_set))

    # Non-selected tuples
    print
    print "NON SELECTED TUPLES:"
    sqn_unselected_set = set()
    unselected_count = 0
    for t in sorted(root_types, key=lambda k: u' '.join(k[0]).replace(u'+', u'')):
        if t[1] or len(type_tuples[t]) >= TYPE_TUPLE_MIN_CAPACITY: continue
        # Print only core tuples
        print "Tuple[*] %s + %s: %d" % (t[0], t[1], len(type_tuples[t]))
        unselected_count += 1
        sqn_unselected_set.update(type_tuples[t])
    print "Total tuples (w/ unselected): %d of %d total" % (sum(num_tuples.values()) + unselected_count, len(type_tuples))
    print "Total SQN (w/ unselected): %d (%d%%) selected of %d total" % (
        len(sqn_selected_set) + len(sqn_unselected_set),
        100.0 * (len(sqn_selected_set) + len(sqn_unselected_set)) / len(sqn_all_set), len(sqn_all_set))


    for num in sorted(num_tuples.iterkeys(), reverse=True):
        print "    %d: %d" % (num, num_tuples[num])


def print_weights(pfqn_parser):
    for dict_i in (pfqn_parser.weights, pfqn_parser.fats, pfqn_parser.packs):
        print "#" * 20
        print "\r\n".join(["%s [%d]" % (k, v) for k, v in sorted(dict_i.iteritems(), key=lambda t: t[1], reverse=True)])
    print "NO-WEIGHT Product Types " + "=" * 60
    c = 0
    for t, d in pfqn_parser.types.iteritems():
        if not d["weight"]:
            print t,
            print '     => fat: %s, pack: %s' % (d["fat"], d["pack"]) if d["fat"] or d["pack"] else ""
            c += 1
    print "Total: %d" % c


if __name__ == '__main__':

    __config = main_options(argv)

    __pfqnParser = main_parse_products(**__config)

    # ############ PRINT RESULTS ##################
    toprint = __config["toprint"]
    if toprint == "brands":
        print_brands()

    elif toprint == "producttypes":
        print_product_types(__pfqnParser)

    elif toprint == "typetuples":
        print_type_tuples(__pfqnParser)

    elif toprint == "weights":
        print_weights(__pfqnParser)

    else:
        raise Exception("Unknown print type [%s]" % toprint)


