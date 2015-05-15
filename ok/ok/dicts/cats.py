# -*- coding: utf-8 -*-

# Classes and procedures to process category data from crawler's CSV output
import csv

from ok.dicts import main_options
from ok.items import CatItem, ROOT_CAT_ITEM


class Cats(dict):

    def __init__(self, iterable=None, **kwargs):
        if iterable:
            super(Cats, self).__init__(iterable, **kwargs)
        else:
            super(Cats, self).__init__(**kwargs)

        self.parentIdx = dict()
        """@type: dict of (str, list[str]) """

        self.product_to_cats = dict()
        """@type: dict of (str, list[str])"""

    def from_csv(self, catcsvname):
        with open(catcsvname, "rb") as f:
            reader = csv.reader(f)
            fields = next(reader)
            for row in reader:
                cat = dict(zip(fields,row))
                item = CatItem(cat)
                item["level"] = int(item["level"])
                item["pathTitles"] = str(item["pathTitles"]).split("|") if item["pathTitles"] else []
                item["products"] = str(item["products"]).split("|") if item["products"] else []
                item["productCount"] = int(item["productCount"]) if item["productCount"] else None
                self[item["id"]] = item
                if item["parentId"]:
                    pIdx = self.parentIdx.get(item["parentId"], [])
                    pIdx.append(item["id"])
                    self.parentIdx[item["parentId"]] = pIdx
                for product_id in item["products"]:
                    self.product_to_cats[product_id] = self.product_to_cats.get(product_id, [])
                    self.product_to_cats[product_id].append(item["id"])

    def find_by_title(self, title):
        """
        Iterate through all categories and find one with specified title ignoring case.
        If many matches 've been found - raise Exception
        @param unicode title: name
        @return Category ID or None
        @rtype: str
        """
        ids_found = [item["id"] for item in self.itervalues() if item["title"].decode("utf-8").lower() == title.lower()]
        if len(ids_found) > 1:
            raise Exception("Multiple categories 've been found with title '%s'" % title)
        return ids_found[0] if ids_found else None

    def is_product_under(self, product_id, cat_id, deep=True):
        """
        Check if product is in products list of specified category or any its descendant
        @param str product_id: Product
        @param str cat_id: parent Category
        @param bool deep: if False only check specified category w/o go down
        @rtype: bool
        """
        if cat_id not in self:
            raise Exception("No category with id[%s]" % cat_id)

        result = False
        cached_cat_ids = self.product_to_cats.get(product_id)
        if cached_cat_ids:
            ancestor_cats = cached_cat_ids[:]
            root_id = ROOT_CAT_ITEM["id"]
            while ancestor_cats:
                # Check if c_cat is specified cat or it is ancestor
                c_cat_id = ancestor_cats.pop()
                if c_cat_id == cat_id:
                    result = True
                    break
                c_parent_id = self.get_parent_id(c_cat_id)
                if c_parent_id and c_parent_id != root_id:
                    ancestor_cats.append(c_parent_id)

        else:
            item = self[cat_id]
            result = product_id in item["products"]
            if not result and deep:
                result = any(self.is_product_under(product_id, sub_cat_id, True) for sub_cat_id in self.parentIdx.get(cat_id, []))
        return result

    def get_parent_id(self, cat_id):
        """
        @param cat_id: Cat id
        @return: parent cat id if parent category is present, otherwise -1 (ROOT_CAT_ITEM["id"])
        """
        if cat_id not in self:
            raise Exception("No category with id[%s]" % cat_id)
        return self[cat_id]["parentId"] or ROOT_CAT_ITEM["id"]

    def get_root_cats(self):
        """
        @return: Return cats titles without parent or where parent is ROOT
        @rtype: list[unicode]
        """
        return sorted(
            cat_item["title"].decode("utf-8")
            for cat_item in self.values()
            if cat_item["id"] != ROOT_CAT_ITEM["id"] and self.get_parent_id(cat_item["id"]) == ROOT_CAT_ITEM["id"]
        )

if __name__ == '__main__':
    config = main_options()
    cat_csvname = config["cat_csvname"]
    cats = Cats()
    cats.from_csv(cat_csvname)

    line = [cats[ROOT_CAT_ITEM["id"]]]
    while line:
        item = line.pop()
        print "%s => %s%s" % (item["id"], " " * ((item["level"]+1)*4), item["title"]),
        print " (%s/%d)" % (item["productCount"], len(item["products"])) if item["productCount"] or item["products"] else ""
        line.extend([cats[childId] for childId in cats.parentIdx.get(item["id"], [])])
        try:
            line.index(item)
            raise Exception("Recursive loop in cats")
        except ValueError:
            pass




