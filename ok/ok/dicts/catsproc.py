# -*- coding: utf-8 -*-

# Classes and procedures to process category data from crawler's CSV output
import csv
from sys import argv
from ok.items import CatItem, ROOT_CAT_ITEM

if __name__ == '__main__':
    catcsvname = argv[1]
    cats = dict()
    """ @type cats: dict of (str, CatItem)"""
    parentIdx = dict()
    """ @type parentIIdx: dict of (str, list[str]) """
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
            cats[item["id"]] = item
            if item["parentId"]:
                pIdx = parentIdx.get(item["parentId"], [])
                pIdx.append(item["id"])
                parentIdx[item["parentId"]] = pIdx

    line = [cats[ROOT_CAT_ITEM["id"]]]
    while line:
        item = line.pop()
        print "%s => %s%s" % (item["id"], " " * ((item["level"]+1)*4), item["title"]),
        print " (%s/%d)" % (item["productCount"], len(item["products"])) if item["productCount"] or item["products"] else ""
        line.extend([cats[childId] for childId in parentIdx.get(item["id"], [])])
        try:
            line.index(item)
            raise Exception("Recursive loop in cats")
        except ValueError:
            pass




