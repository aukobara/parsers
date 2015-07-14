# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

import csv

from ok.utils import to_str

PRODUCT_ATTRIBUTE_RAW_ID = 'raw_id'


class Product(dict):

    # Product class itself should not have any fields except dictionary data
    __slots__ = ()
    validators = dict()
    """@type: dict of (str, callable)"""

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

    def __hash__(self):
        return self.pfqn.__hash__()

    @property
    def raw_item(self):
        """
        @rtype: dict
        """
        return self.get('raw_item', dict())

    def _validate_raw_item(self, raw_item):
        if not all(hasattr(raw_item, attr) for attr in ('__contains__', '__getitem__')):
            raise Exception('Raw_item must be dict but %s comes to Product[pfqn=%s]' % (type(raw_item), self.pfqn))
    validators['raw_item'] = _validate_raw_item

    @raw_item.setter
    def raw_item(self, raw_item):
        self["raw_item"] = raw_item

    def __contains__(self, key):
        if key == PRODUCT_ATTRIBUTE_RAW_ID and 'id' in self.raw_item:
            return True
        return dict.__contains__(self, key)

    def __getitem__(self, key):
        if key == PRODUCT_ATTRIBUTE_RAW_ID and 'id' in self.raw_item:
            return self.raw_item['id']
        return dict.__getitem__(self, key)

    def _validate(self, key, value):
        if key in self.validators:
            self.validators[key](self, value)

    def __setitem__(self, key, value):
        self._validate(key, value)
        dict.__setitem__(self, key, value)

    def update(self, other=None, **kwargs):
        val = dict(other or {})
        val.update(kwargs)
        for k, v in val.items():
            self._validate(k, v)
        dict.update(self, other, **kwargs)

    @staticmethod
    def to_meta_csv(csv_filename, products):
        """
        Store parsed products metadata to use for further analysis and product lookup
        @param csv_filename: file name
        @param collections.Iterable[Product] products: products' iterator to export
        """
        with open(csv_filename, 'wb') as f:
            f.truncate()
            header = [PRODUCT_ATTRIBUTE_RAW_ID, 'sqn', 'brand', 'brand_detected', 'product_manufacturer', 'weight', 'fat', 'pack', 'pfqn', 'tags', 'types']
            writer = csv.DictWriter(f, header)
            writer.writeheader()
            for product in products:
                d = dict()
                for field in header:
                    if field in product:
                        value = product[field]
                        if isinstance(value, (list, tuple, set)):
                            value = u'|'.join(sorted(map(to_str, value)))
                        d[field] = to_str(value).encode("utf-8")

                writer.writerow(d)

    @staticmethod
    def from_meta_csv(csv_filename):
        """
        Load parsed products metadata to use for further analysis and product lookup
        @param csv_filename: file name
        @return: generator of Products
        @rtype: collections.Iterable[Product]
        """
        from ok.dicts.product_type import ProductType

        def reformat_attr(_product, field):
            if field in product and product.get(field) is not None:
                value = product[field]
                product[field] = value.split(' + ') if ' + ' in value else value

        with open(csv_filename, 'rb') as f:
            reader = csv.reader(f)
            fields = next(reader)
            for row in reader:
                product_meta_row = dict(zip(fields, row))
                product = Product(**{field: value.decode("utf-8") for field, value in product_meta_row.items()})
                if 'tags' in product and product.get('tags') is not None:
                    product['tags'] = set(product['tags'].split('|'))
                else:
                    product['tags'] = set()
                if 'types' in product and product.get('types') is not None:
                    product['types'] = set([ProductType(*pt_str.split(' + ')) for pt_str in product['types'].split('|')])
                else:
                    product['types'] = set()
                reformat_attr(product, 'fat')
                reformat_attr(product, 'weight')
                reformat_attr(product, 'pack')
                yield product
