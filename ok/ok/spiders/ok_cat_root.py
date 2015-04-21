# coding: cp1251
import scrapy
from scrapy.spider import Spider
from ok.items import CatItem, ProductItem

'''//*[@id="departmentLink_16568_alt"]'''
'''<a id="departmentLink_16568_alt" href="http://www.okeydostavka.ru/msk/..." aria-haspopup="true" data-toggle="departmentMenu_16568" 
	class="link menuLink" data-parent="allDepartmentsMenu" role="menuitem" tabindex="-1">
										title
	</a>'''


class RootCatSpider(Spider):
    name = "ok"
    allowed_domains = ["okeydostavka.ru"]
    start_urls = ["http://www.okeydostavka.ru/msk/catalog"]
    # start_urls = ["http://www.okeydostavka.ru/msk/%D0%BC%D0%BE%D0%BB%D0%BE%D1%87%D0%BD%D1%8B%D0%B5-%D0%BF%D1%80%D0%BE%D0%B4%D1%83%D0%BA%D1%82%D1%8B--%D1%81%D1%8B%D1%80%D1%8B--%D1%8F%D0%B9%D1%86%D0%BE/%D0%BC%D0%BE%D0%BB%D0%BE%D1%87/%D1%81%D0%BC%D0%B5%D1%82%D0%B0%D0%BD%D0%B0"]

    def __init__(self):
        with open("catlog.txt", "w") as f:
            f.truncate()
        # self.download_delay = 1/2

    def extractA(self, selA):
        text = selA.xpath("text()").extract()[0].strip()
        url = selA.xpath("@href").extract()[0]
        return url, text

    def extractProd(self, selP):
        if not selP.xpath(".//div[@class='product_name']/a/text()").extract():
            return None

        item = ProductItem()
        item ["name"] = selP.xpath(".//div[@class='product_name']/a/text()").extract()[0].strip()
        item ["link"] = selP.xpath(".//div[@class='product_name']/a/@href").extract()[0]
        item ["imgUrl"] = selP.xpath(".//div[@class='image']//img/@src").extract()[0]
        item ["weight"] = ' '.join([txt.strip() for txt in selP.xpath(".//div[@class='product_weight']/span/text()").extract()])
        selPrice = selP.xpath(".//span[@class='product_price']/span/text()")
        item ["price"] = selPrice.extract()[0].strip() if selPrice else None
        return item


    def catlog(self, level, item):
        with open("catlog.txt", "ab") as f:
            f.write("%d: %s%s\n" % (level, " " * level, ' '.join(item["title"])))

    def parse(self, response):
        catsSel = response.xpath("//ul[@id='categoryMenu']//a[@class=\"link menuLink\"]")
        if not catsSel:
            # home page? all dep menu
            if response.xpath("//div[@id='homePageMenu']"):
                catsSel = response.xpath("//a[@class=\"link menuLink\"]")
        for topCat in catsSel:
            item = CatItem()
            item["link"], item["title"] = self.extractA(topCat)
            self.catlog(0, item)

            # yield item
            if item["link"]:
                yield scrapy.Request(item["link"], callback=self.parse)

        for prodSel in response.xpath("//div[@class='product_listing_container']//div[contains(concat(' ', @class, ' '), ' product ')]"):
            item = self.extractProd(prodSel)
            if item:
                yield item
                yield scrapy.Request(item["link"], callback=self.parseProductDetails)

    def parseProductDetails(self, response):
        pass

