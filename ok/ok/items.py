# -*- coding: utf-8 -*-

# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html
import json

import scrapy

class CatItem(scrapy.Item):
    # define the fields for your item here like:
    # name = scrapy.Field()
    title = scrapy.Field()
    link = scrapy.Field()


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
