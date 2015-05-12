# -*- coding: utf-8 -*-

import csv
import re
import json
from sys import argv

from ok.items import ProductItem
from ok.dicts import cleanup_token_str, remove_nbsp
from ok.dicts.brand import Brand
from ok.dicts.catsproc import Cats


ATTRIBUTE_BRAND = u"Бренд:"
ATTRIBUTE_MANUFACTURER = u"Изготовитель:"
ATTRIBUTE_WEIGHT = u"Вес:"

# prefix can be consumed by re parser and must be returned in sub - must be always 1st Match
RE_TEMPLATE_PFQN_PRE = u'(?:\s|\.|,|\()'
# post is predicate and isn't consumed by parser. but must start immediately after term group
RE_TEMPLATE_PFQN_POST = u'(?=\s|$|,|\.|\)|/)'

RE_TEMPLATE_PFQN_WEIGHT_FULL = u'(\D)(' +\
                u'(?:\d+(?:шт|пак)?\s*(?:х|\*|x|/))?\s*' +\
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
                        u'(т/пак|ж/б|ст/б|м/у|с/б|ст\\\б|ст/бут|пл/б|пл/бут|пэтбутылка|пл|кор\.?' + \
                        u'|\d*\s*пак\.?|\d+\s*таб|\d+\s*саше|\d+\s*пир(?:\.|амидок)?' + \
                        u'|(?:\d+\s*)?шт\.?|упак\.?|уп\.?|в/у|п/э|жесть|' \
                        u'вакуум|нарезка|нар|стакан|ванночка|в\sванночке|дой-пак|дой/пак|пюр-пак|пюр\sпак|' + \
                        u'зип|зип-пакет|д/пак|п/пак|пл\.упаковка|пэт|пакет|туба|ведро|бан|лоток|фольга' + \
                        u'|фас(?:ованные)?|н/подл\.?|ф/пакет|0[.,]5|0[.,]75|0[.,]33)' + RE_TEMPLATE_PFQN_POST


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

    __pfqn_re_weight_full = re.compile(RE_TEMPLATE_PFQN_WEIGHT_FULL)
    __pfqn_re_weight_short = re.compile(RE_TEMPLATE_PFQN_WEIGHT_SHORT)
    __pfqn_re_fat = re.compile(RE_TEMPLATE_PFQN_FAT)
    __pfqn_re_pack = re.compile(RE_TEMPLATE_PFQN_PACK)

    def __init__(self):
        self.types = dict()
        """ @type types: dict of (unicode, Product) """
        self.weights = dict()
        self.fats = dict()
        self.packs = dict()

        self.ignore_category_id_list = None
        self.cats = Cats()

    def use_cats_from_csv(self, cat_csvname):
        self.cats.from_csv(cat_csvname)

    def ignore_cats(self, *ignore_cat_names):
        for cat_name in ignore_cat_names:
            id = self.cats.find_by_title(cat_name)
            if id:
                self.ignore_category_id_list = self.ignore_category_id_list or []
                self.ignore_category_id_list.append(id)

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

                if self.ignore_category_id_list and any(self.cats.is_product_under(item["id"], cat_id) for cat_id in self.ignore_category_id_list if cat_id):
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
                        if not brand.no_brand:
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
                sqn_without_brand = manufacturer_brand.replace_brand(sqn_without_brand)
                if sqn_last_change != sqn_without_brand:
                    product.sqn = sqn_without_brand
                    product["brand_detected"] = True
                    no_brand_replacements.append((sqn_last_change, sqn_without_brand))
                    sqn_last_change = sqn_without_brand
        return no_brand_replacements

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

            for brand in Brand.all(skip_no_brand=True):
                sqn_without_brand = brand.replace_brand(product.sqn, add_new_synonyms=False)
                if product.sqn != sqn_without_brand:
                    print u"Brand [%s] may be in product type [sqn:%s, brand: %s, manufacturer: %s]" % \
                          (brand.name + u'|' + u'|'.join(brand.get_synonyms()),
                           product.sqn, product["brand"], product["product_manufacturer"])

if __name__ == '__main__':

    opts = argv[:]
    prodcsvname = opts[1]
    toprint = "producttypes"  # default
    cat_csvname = None  # Don't pre-load categories by default
    brands_in_csvname = None  # Don't load brands by default
    brands_out_csvname = None  # Don't save brands by default
    while len(opts) > 2:
        opt = opts.pop(2)
        if opt == "-p" and len(opts) > 2:
            toprint = opts.pop(2)
        elif opt == "-c" and len(opts) > 2:
            cat_csvname = opts.pop(2)
        elif opt == "-in-brands-csv" and len(opts) > 2:
            brands_in_csvname = opts.pop(2)
        elif opt == "-out-brands-csv" and len(opts) > 2:
            brands_out_csvname = opts.pop(2)
        else:
            raise Exception("Unknown options")

    pfqnParser = ProductFQNParser()

    if cat_csvname is not None:
        pfqnParser.use_cats_from_csv(cat_csvname)
        print "Categories've been loaded from '%s': %d" % (cat_csvname, len(pfqnParser.cats))
    pfqnParser.ignore_cats(u"Алкогольные напитки", u"Скидки")

    if brands_in_csvname is not None:
        Brand.from_csv(brands_in_csvname)
        print "Brands and manufacturers 've been loaded from '%s': %d" % (brands_in_csvname, len(Brand.all()))

    pfqnParser.from_csv(prodcsvname)
    pfqnParser.process_manufacturers_as_brands()

    enabled_brand_guesses = False
    if enabled_brand_guesses:
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

    # ############ PRINT RESULTS ##################

    if toprint == "brands":
        manufacturers = dict()
        """ @type manufacturers: dict of (unicode, list[unicode]) """
        for b in Brand.all():
            print b
            for m in b.manufacturers:
                manufacturers[m] = manufacturers.get(m, [])
                manufacturers[m].append(b.name)
                manufacturers[m] += map(lambda s: "~"+s, b.synonyms)
        print "Total brands: %d" % len(Brand.all())
        print
        for m, b in sorted(manufacturers.iteritems(), key=lambda t:t[0]):
            print "%s [%s]" % (m, "|".join(b))
            for linked_m in [im for ib in b if Brand.exist(ib) for im in Brand.exist(ib).manufacturers
                             if im != m and ib not in Brand.no_brand_names() and (ib != u"О'КЕЙ" or m == u"ООО \"О'КЕЙ\"")]:
                print "    ==> %s [%s]" % (linked_m, "|".join(manufacturers[linked_m]))
        print "Total manufacturers: %d" % len(manufacturers)

    elif toprint == "producttypes":
        ptypes_count = 0
        nobrand_count = 0
        m_count = dict()
        # for t, d in sorted(types.iteritems(), key=lambda t: t[1]["sqn"].split(" ", 1)[0]):
        for t, d in sorted(pfqnParser.types.iteritems(), key=lambda t: t[1]["product_manufacturer"]):
            if not d["brand_detected"] and (d["brand"] in Brand.no_brand_names()):
                # print '%s   => brand: %s, prod_man: %s, weight: %s, fat: %s, pack: %s, fqn: %s' % \
                #       (d["sqn"], d["brand"], d["product_manufacturer"], d["weight"], d["fat"], d["pack"], t)
                nobrand_count += 1

            elif not d["brand_detected"]:
                print '%s   => brand: %s, prod_man: %s, weight: %s, fat: %s, pack: %s, fqn: %s' % \
                     (d["sqn"], d["brand"], d["product_manufacturer"], d["weight"], d["fat"], d["pack"], t)
                m_count[d["brand"]] = m_count.get(d["brand"], 0)
                m_count[d["brand"]] += 1
                ptypes_count += 1
        print
        print "Total product types: %d [notintype: %d, nobrand: %d]" % (len(pfqnParser.types), ptypes_count, nobrand_count)
        print
        for m, c in sorted(m_count.iteritems(), key=lambda t:t[1], reverse=True):
            print "%d : %s" % (c, m)

    elif toprint == "typetuples":
        types2 = dict()
        for t, d in sorted(pfqnParser.types.iteritems(), key=lambda t: t[1]["sqn"].split(" ", 1)[0]):
            words = re.split(u'\s+', d["sqn"])
            first_word = words.pop(0)
            if not words:
                words.append(u'')
            buf = ''
            for w in words:
                if w or len(words) == 1:
                    if w in [u'в', u'с', u'со', u'из', u'для', u'и', u'на', u'без', u'к', u'не']:
                        buf = w  # join proposition to the next word
                        continue
                    w = buf + u' ' + w if buf else w
                    types2[(first_word, w)] = types2.get((first_word, w), 0) + 1
                    buf = u''

        num_tuples = dict()
        # for t, c in sorted(types2.iteritems(), key=lambda k: types2[k[0]], reverse=True):
        for t, c in sorted(types2.iteritems(), key=lambda k: k[0][0]):
            if c <= 1: continue
            print "Tuple %s + %s: %d" % (t[0], t[1], c)
            num_tuples[c] = num_tuples.get(c, 0) + 1
        print "Total tuples: %d" % sum(num_tuples.values())
        for num in sorted(num_tuples.iterkeys(), reverse=True):
            print "    %d: %d" % (num, num_tuples[num])

    elif toprint == "weights":
        for dict_i in (pfqnParser.weights, pfqnParser.fats, pfqnParser.packs):
            print "#" * 20
            print "\r\n".join(["%s [%d]" % (k, v) for k,v in sorted(dict_i.iteritems(), key=lambda t:t[1], reverse=True)])

        print "NO-WEIGHT Product Types " + "=" *60
        c = 0
        for t, d in pfqnParser.types.iteritems():
            if not d["weight"]:
                print t,
                print '     => fat: %s, pack: %s' % (d["fat"], d["pack"]) if d["fat"] or d["pack"] else ""
                c+=1
        print "Total: %d" % c

    else:
        raise Exception("Unknown print type [%s]" % toprint)


