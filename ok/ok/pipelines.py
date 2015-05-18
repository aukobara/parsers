# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html
from scrapy.exceptions import DropItem
from items import ProductItem


class OkPipeline(object):

    ids = set()

    def process_item(self, item, spider):
        if isinstance(item, ProductItem):
            productId = item["id"]
            if productId:
                if productId in self.ids:
                    raise DropItem("Product is processed already %r, crawllink: %r" %
                                   (productId, item.get("crawllink", '<no-link>')))
                else:
                    self.ids.add(productId)
        return item
