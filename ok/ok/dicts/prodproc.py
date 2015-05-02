# -*- coding: utf-8 -*-

# Classes and procedures to process category data from crawler's CSV output
import csv
import re
from sys import argv
from ok.items import ProductItem
import json

ATTRIBUTE_BRAND = u"Бренд:"
ATTRIBUTE_MANUFACTURER = u"Изготовитель:"
ATTRIBUTE_WEIGHT = u"Вес:"

class Brand(object):
    # TODO: Assert everything in class as unicode
    # TODO: Add single place to define default(N/A)/NoBrand

    _brands = dict()
    """ @type __brands: dict of (unicode, Brand) """

    @classmethod
    def to_key(cls, name):
        return (name if isinstance(name, unicode) else unicode(name, "utf-8")).lower()

    @classmethod
    def findOrCreate(cls, name):
        exist = cls._brands.get(cls.to_key(name))
        return exist or cls(name)

    @classmethod
    def all(cls):
        """
        @rtype: list[Brand]
        """
        return sorted(cls._brands.values(), key=lambda b: b.name)

    def __init__(self, name = "N/A"):
        self.name = name if isinstance(name, unicode) else unicode(name, "utf-8")
        self.manufacturers = set()
        self.__class__._brands[self.__class__.to_key(self.name)] = self
        self.synonyms = []
        self.generic_type = None

    def __eq__(self, other):
        return isinstance(other, Brand) and self.name == other.name

    def __str__(self):
        return ("%s [synonyms: %s][m:%s]" % (self.name, "|".join(self.synonyms), "|".join(self.manufacturers))).encode("utf-8")


def configure():
    prodcsvname = argv[1]
    toprint = "producttypes"  # default
    if len(argv) > 2:
        opt = argv[2]
        if opt == "-p" and len(argv) > 3:
            toprint = argv[3]
        else:
            raise Exception("Unknown options")

    # Pre-load brand synonyms
    Brand.findOrCreate(unicode("О'КЕЙ", "utf-8")).synonyms += [u"ОКЕЙ"]
    Brand.findOrCreate(u"Kotany").synonyms += [u"Kotanyi"]
    Brand.findOrCreate(u"Витамин").synonyms += [u"vитамин"]
    Brand.findOrCreate(u"VITAMIN").synonyms += [u"Vитамин"]
    Brand.findOrCreate(u"Хлебцы-Молодцы").generic_type = u"Хлебцы"
    Brand.findOrCreate(u"Сиртаки").generic_type = u"Брынза"
    Brand.findOrCreate(u"Чупа Чупс").generic_type = u"Чупа Чупс"
    Brand.findOrCreate(u"Vitaland").synonyms += [u"Виталэнд"]
    Brand.findOrCreate(u"Активиа").synonyms += [u"Активия"]
    Brand.findOrCreate(u"PL NoName").synonyms += [u"PL FP"]
    Brand.findOrCreate(u"TM Mlekara Subotica").synonyms += [u"Mlekara Subotica"]

    return (prodcsvname, toprint)


def parse_pfqn(pfqn):
    """
    Parse Full Product Name and return name parts: type, brand, weight, fat, etc
    TODO: Some pfqn can have multiple entries, use list/dict instead of tuple
    @param unicode pfqn: Full Product Name
    @rtype: (unicode, unicode, unicode, unicode)
    """
    pfqn = pfqn.lower()
    pre = u'(?:\s|\.|,|\()'  # prefix can be consumed by re parser and must be returned in sub - must be always 1st Match
    post = u'(?=\s|$|,|\.|\)|/)'  # post is predicate and isn't consumed by parser. but must start immediately after term group

    def _add_match(ll, match):
        _pre = match.group(1)
        _m = match.group(2)
        ll[0] = (ll[0] + u" + " if ll[0] else "") + _m.strip()
        return _pre

    # weight - if has digit should be bounded by non-Digit, if has no digit - than unit only is acceptable but as token
    wl = [u""]
    pfqn = re.sub(u'(\D)('
                u'(?:\d+(?:шт)?(?:х|\*|x|/))?'
                u'(?:\d+(?:[\.,]\d+)?\s*)'
                u'(?:кг|г|л|мл|гр)\.?'
                u'(?:(?:х|\*|x|/)\d+(?:\s*шт)?)?'
                u')' + post,
           lambda g: _add_match(wl, g),
           pfqn
           )
    if not wl[0]:
        pfqn = re.sub( u'(\D' + pre + u')((?:кг|г|л|мл|гр)\.?)' + post,
                        lambda g: _add_match(wl, g),
                        pfqn )
    # fat
    fl=[u""]
    pfqn = re.sub( u'(' + pre + u')(\d+(?:[\.,]\d*)?\s*%(?:\s*жирн\.?)?)' + post,
                   lambda g: _add_match(fl, g), pfqn )
    # pack
    pl=[u""]
    pfqn = re.sub( u'(' + pre + u')'
                  u'(т/пак|ж/б|ст/б|ст/бут|пл/б|пл/бут|пэтбутылка|кор\.?|\d+\s*пак\.?|\d+\s*пир\.?|(?:\d+\s*)?шт\.?|упак\.?|уп\.?|в/у|п/э|жесть|'
                  u'стакан|дой-пак|д/пак|пакет|ведро|лоток|фольга|фас(?:ованные)?|н/подл\.?|ф/пакет|0[.,]5|0[.,]75|0[.,]33)' + post,
                   lambda g: _add_match(pl, g), pfqn )
    return wl[0], fl[0], pl[0], pfqn


def isenglish(s):
    try:
        (s.encode("utf-8") if isinstance(s, unicode) else s).decode('ascii')
        return True
    except UnicodeDecodeError:
        return False


def isrussian(s):
    if isenglish(s):
        return False
    try:
        (s.encode("utf-8") if isinstance(s, unicode) else s).decode('cp1251')
        return True
    except UnicodeDecodeError:
        return False


def replace_brand(s, brand, rs):
    """
    Replace brand name in string s to rs. Only full words will be replaced.
    Brand synonyms are iterated to check different variants.
    Quotation are treated as part of brand name substring.
    TODO: Check spelling errors and translitiration
    @param unicode s: original string
    @param Brand brand: brand entity with synonyms
    @param unicode rs: replacement
    @return: Updated string if brand is found, original string otherwise
    @rtype unicode
    """
    if not s: return s
    brand_variants = [brand.name] + brand.synonyms
    result = s
    # Start with longest brand names to avoid double processing of shortened names
    for b in sorted(brand_variants, key=len, reverse=True):
        pos = result.lower().find(b.lower())
        while pos >= 0:
            pre_char = result[pos-1] if pos > 0 else u""
            post_char = result[pos+len(b)] if pos+len(b) < len(result) else u""
            if not pre_char.isalnum() and (not post_char.isalnum() or (isenglish(b[-1]) and isrussian(post_char))):  # Brand name is bounded by non-alphanum
                result = result[:pos] + rs + result[pos+len(b):]
                pos += len(rs)
            else:
                print (u"Suspicious string [%s] may contain brand name [%s]" % (s, b))
                pos += len(b)
            pos = result.lower().find(b.lower(), pos)

    return result


if __name__ == '__main__':
    (prodcsvname, toprint) = configure()

    types = dict()
    """ @type types: dict of (unicode, dict of (str, unicode)) """
    weights = dict()
    fats = dict()
    packs = dict()
    with open(prodcsvname, "rb") as f:
        reader = csv.reader(f)
        fields = next(reader)
        for row in reader:
            prodrow = dict(zip(fields, row))
            item = ProductItem(prodrow)
            pfqn = unicode(item["name"], "utf-8")

            if item.get("details"):
                details = json.loads(item["details"])
                """ @type details: dict of (unicode, unicode) """

                brand = Brand.findOrCreate(details.get(ATTRIBUTE_BRAND, "N/A"))

                if details.get(ATTRIBUTE_MANUFACTURER):
                    brand.manufacturers.add(details.get(ATTRIBUTE_MANUFACTURER))
            else:
                brand = Brand.findOrCreate(u"N/A")

            (weight, fat, pack, sqn) = parse_pfqn(pfqn)
            def __fill_fqn_dict(d, item):
                for k in item.split(u" + "): d[k] = d.get(k, 0) + 1
            __fill_fqn_dict(weights, weight)
            __fill_fqn_dict(fats, fat)
            __fill_fqn_dict(packs, pack)

            sqn = replace_brand(sqn, brand, " " if not brand.generic_type else u" " + brand.generic_type + u" ") if brand.name != u"N/A" else sqn
            types[pfqn] = dict(weight=weight, fat=fat, pack=pack, brand=brand.name, sqn=sqn)

    if toprint == "brands":
        manufacturers = dict()
        for b in Brand.all():
            print b
            for m in b.manufacturers:
                manufacturers[m] = manufacturers.get(m, [])
                manufacturers[m].append(b.name)
        print "Total brands: %d" % len(Brand.all())
        print
        for m, b in manufacturers.iteritems():
           print "%s [%s]" % (m, "|".join(b))
        print "Total manufacturers: %d" % len(manufacturers)

    elif toprint == "producttypes":
        for t, d in sorted(types.iteritems(), key=lambda t: t[1]["sqn"].split(" ", 1)[0]):
            print '%s   => brand: %s, weight: %s, fat: %s, pack: %s, fqn: %s' % \
                  (d["sqn"], d["brand"], d["weight"], d["fat"], d["pack"], t)

    elif toprint == "weights":
        for dict_i in (weights, fats, packs):
            print "#" * 20
            print "\r\n".join(["%s [%d]" % (k, v) for k,v in sorted(dict_i.iteritems(), key=lambda t:t[1], reverse=True)])

        print "NO-WEIGHT Product Types " + "=" *60
        c = 0
        for t, d in types.iteritems():
            if not d["weight"]:
                print t,
                print '     => fat: %s, pack: %s' % (d["fat"], d["pack"]) if d["fat"] or d["pack"] else ""
                c+=1
        print "Total: %d" % c

    else:
        raise Exception("Unknown print type [%s]" % toprint)


