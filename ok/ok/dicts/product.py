# -*- coding: utf-8 -*-
import csv


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

    @staticmethod
    def to_meta_csv(csv_filename, products):
        """
        Store parsed products metadata to use for further analysis and product lookup
        @param csv_filename: file name
        @param collections.Iterable[Product] products: products' iterator to export
        """
        with open(csv_filename, 'wb') as f:
            f.truncate()
            header = ['raw_id', 'sqn', 'brand', 'brand_detected', 'product_manufacturer', 'weight', 'fat', 'pack', 'pfqn']
            writer = csv.DictWriter(f, header)
            writer.writeheader()
            for product in products:
                d = {field: unicode(product[field]).encode("utf-8") for field in header if product.get(field)}
                d['raw_id'] = product["raw_item"]["id"]
                writer.writerow(d)

        pass

    @staticmethod
    def from_meta_csv(csv_filename):
        """
        Load parsed products metadata to use for further analysis and product lookup
        @param csv_filename: file name
        @return: generator of Products
        @rtype: collections.Iterable[Product]
        """
        with open(csv_filename, 'rb') as f:
            reader = csv.reader(f)
            fields = next(reader)
            for row in reader:
                product_meta_row = dict(zip(fields, row))
                product = Product(**{field: value.decode("utf-8") for field, value in product_meta_row.iteritems()})
                yield product
        pass