# -*- coding: utf-8 -*-

# Classes and procedures to process category data from crawler's CSV output
import csv
from sys import argv
from ok.items import CatItem, ROOT_CAT_ITEM, ProductItem
import json

ATTRIBUTE_BRAND = u"Бренд:"
ATTRIBUTE_MANUFACTURER = u"Изготовитель:"

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


if __name__ == '__main__':
    prodcsvname = argv[1]
    with open(prodcsvname, "rb") as f:
        reader = csv.reader(f)
        fields = next(reader)
        for row in reader:
            prodrow = dict(zip(fields,row))
            item = ProductItem(prodrow)
            if item.get("details"):
                details = json.loads(item["details"])
                name = details.get(ATTRIBUTE_BRAND, "N/A")
                brand = Brand.findOrCreate(name)
                if details.get(ATTRIBUTE_MANUFACTURER):
                    brand.manufacturers.add(details.get(ATTRIBUTE_MANUFACTURER))

    for b in Brand.all():
        print b
    print "Total brands: %d" % len(Brand.all())



