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

    _brands = dict()
    """ @type __brands: dict of (unicode, Brand) """

    @classmethod
    def findOrCreate(cls, name):
        exist = cls._brands.get(name.lower())
        return exist or cls(name)

    @classmethod
    def all(cls):
        """
        @rtype: list[Brand]
        """
        return sorted(cls._brands.values(), key=lambda b: b.name)

    def __init__(self, name = "N/A"):
        self.name = name
        self.manufacturers = set()
        self.__class__._brands[name.lower()] = self

    def __eq__(self, other):
        return isinstance(other, Brand) and self.name == other.name

    def __str__(self):
        return ("%s [m:%s]" % (self.name, "|".join(self.manufacturers))).encode("utf-8")


def configure():
    prodcsvname = argv[1]
    toprint = "producttypes"  ## default
    if len(argv) > 2:
        opt = argv[2]
        if opt == "-p" and len(argv) > 3:
            toprint = argv[3]
        else:
            raise Exception("Unknown options")
    return (prodcsvname, toprint)


def parse_pfqn(pfqn):
    """
    Parse Full Product Name and return name parts: type, brand, weight, fat, etc
    TODO: Some pfqn can have multiple entries, use list/dict instead of tuple
    @param unicode pfqn: Full Product Name
    @rtype: tuple(unicode)
    """
    pfqn = pfqn.decode("utf-8").lower().encode("utf-8") if not isinstance(pfqn, unicode) else pfqn.lower()
    pre = '(?:\s|\.|,|\()'
    post = '(?=\s|$|,|\.|\)|/)'

    def _add_match(ll, match):
        m = match.group(0)
        ll[0] = (ll[0] + " + " if ll[0] else "") + m.strip()
        return ""

    # weight - if has digit should be bounded by non-Digit, if has no digit - than unit only is acceptable but as token
    wl = [""]
    pfqn = re.sub('\D(' +
                '(?:\d+(?:шт)?(?:х|\*|x|/))?'
                '(?:\d+(?:[\.,]\d+)?\s*)'
                '(?:кг|г|л|мл|гр)\.?'
                '(?:(?:х|\*|x|/)\d+(?:\s*шт)?)?'
                + ')' + post,
           lambda g: _add_match(wl, g),
           pfqn
           )
    if not wl[0]:
        pfqn = re.sub( '(?:\D)' + pre + '((?:кг|г|л|мл|гр)\.?)' + post,
                        lambda g: _add_match(wl, g),
                        pfqn )
    # fat
    fl=[""]
    pfqn = re.sub( pre + '(\d+(?:[\.,]\d*)?\s*%(?:\s*жирн\.?)?)' + post,
                   lambda g: _add_match(fl, g), pfqn )
    # pack
    pl=[""]
    pfqn = re.sub( pre +
                  '(т/пак|ж/б|ст/б|ст/бут|пл/б|пл/бут|кор\.?|\d+\s*пак\.?|\d+\s*пир\.?|(?:\d+\s*)?шт\.?|упак\.?|уп\.?|в/у|п/э|жесть|'
                  'стакан|дой-пак|пакет|ведро|лоток|фольга|фас(?:ованные)?|н/подл\.?|ф/пакет|0[.,]5|0[.,]75|0[.,]33)' + post,
                   lambda g: _add_match(pl, g), pfqn )
    return wl[0], fl[0], pl[0], pfqn

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
            prodrow = dict(zip(fields,row))
            item = ProductItem(prodrow)
            pfqn = item["name"]
            """ @type pfqn: str """

            brand = None
            if item.get("details"):
                details = json.loads(item["details"])

                name = details.get(ATTRIBUTE_BRAND, "N/A").encode("utf-8")
                brand = Brand.findOrCreate(name)

                if details.get(ATTRIBUTE_MANUFACTURER):
                    brand.manufacturers.add(details.get(ATTRIBUTE_MANUFACTURER))

            (weight, fat, pack, sqn) = parse_pfqn(pfqn)
            def __fill_fqn_dict(d, item):
                for k in item.split(" + "): d[k] = d.get(k, 0) + 1
            __fill_fqn_dict(weights, weight)
            __fill_fqn_dict(fats, fat)
            __fill_fqn_dict(packs, pack)

            sqn = sqn.replace(brand.name.decode("utf-8").lower().encode("utf-8"), "") if brand and brand.name != "N/A" else sqn
            types[pfqn] = dict(weight=weight, fat=fat, pack=pack, brand=brand.name if brand else None, sqn=sqn)

    if toprint == "brands":
        for b in Brand.all():
           print b
        print "Total brands: %d" % len(Brand.all())

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


