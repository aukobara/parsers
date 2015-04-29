# -*- coding: utf-8 -*-

# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html
import json
import scrapy

class CatItem(scrapy.Item):
    # define the fields for your item here like:
    # catId, title, crawllink, level, parentId, parent-title|...|top-title, productcount, prodId1|...|prodIdN

    id = scrapy.Field()
    title = scrapy.Field()
    crawllink = scrapy.Field()
    level = scrapy.Field()
    parentId = scrapy.Field()
    pathTitles = scrapy.Field(serializer=lambda list: "|".join(list).encode("utf-8"))  # list of parent-title from bottom to top
    productCount = scrapy.Field()  # count of products in category
    products = scrapy.Field(serializer=lambda list: "|".join(map(str, list)))  # set of productIds in category
    stop = scrapy.Field()  # True if category and all under should not be further processed


ROOT_CAT_ITEM = CatItem({"id": "-1", "title": "ROOT", "level": -1})

class ProductItem(scrapy.Item):
    # define the fields for your item here like:
    id = scrapy.Field() # unique ProductID which can be used for PDP request by canonical url
    name = scrapy.Field()
    imgUrl = scrapy.Field() # small image for grid
    price = scrapy.Field() # offer price
    link = scrapy.Field() # canonical unique universal link to PDP, without referrers, cats and excessive params
    crawllink = scrapy.Field() # link to PDP reachable by crawler from category, can be different than canonical
    weight = scrapy.Field()
    # JSON with key-values on PDP
    details = scrapy.Field(serializer=lambda map: json.dumps(map, ensure_ascii=False).encode("utf-8"))
