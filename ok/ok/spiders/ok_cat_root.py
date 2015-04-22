# coding: cp1251
import scrapy
from scrapy.http.response.text import TextResponse
from ok.items import CatItem, ProductItem
import re

'''//*[@id="departmentLink_16568_alt"]'''
'''<a id="departmentLink_16568_alt" href="http://www.okeydostavka.ru/msk/..." aria-haspopup="true" data-toggle="departmentMenu_16568" 
	class="link menuLink" data-parent="allDepartmentsMenu" role="menuitem" tabindex="-1">
										title
	</a>'''


class RootCatSpider(scrapy.Spider):
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
        """
        @type response: TextResponse
        @param response
        """
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

        pageLinks = self.parseProductListPaging(response)
        for link in pageLinks:
            yield scrapy.Request(link, self.parse)

        for prodSel in response.xpath("//div[@class='product_listing_container']//div[contains(concat(' ', @class, ' '), ' product ')]"):
            item = self.extractProd(prodSel)
            if item:
                yield item
                if item["link"]:
                    yield scrapy.Request(item["link"], callback=self.parseProductDetails)

    def parseProductListPaging(self, response):
        """
        Parse paging links on Product Grid pages

        <div id="pageControlMenu_6_-1011_3074457345618259713" class="pageControlMenu" data-dojo-attach-point="pageControlMenu" data-parent="header">
            <div class="pageControl number">
                <a class="active selected" href="#" role="button" aria-disabled="true" aria-label="Перейти к странице 1" tabindex="-1">1</a>
                <a class="hoverover" role="button" href='javascript:dojo.publish("showResultsForPageNumber",
                    [{pageNumber:"2",pageSize:"72", linkId:"WC_SearchBasedNavigationResults_pagination_link_2_categoryResults"}])'
                    id="WC_SearchBasedNavigationResults_pagination_link_2_categoryResults" aria-label="Перейти к странице 2" title="Перейти к странице 2">2</a>
        Current orderBy: <input type="hidden" name="orderBy" data-dojo-attach-point="valueNode" value="2" aria-hidden="true">
        Link format: {cat-url}#facet:&productBeginIndex:72&orderBy:2&pageView:grid&minPrice:&maxPrice:&pageSize:&
        """
        pageLinks = set()
        pageMenuSel = response.xpath("//div[@class='pageControlMenu']")
        if pageMenuSel:
            baseUrl = response.request.url
            if baseUrl.find("#") < 0:
                baseUrl += "#productBeginIndex:0"
                orderBySel = response.xpath("//div[@class='orderByDropdown selectWrapper']//option[@selected]/@value")
                if orderBySel:
                    baseUrl += "&orderBy:%d" % int( orderBySel[0].extract() )
            for jslinkSel in pageMenuSel.xpath(".//a[contains(@href, 'pageNumber')]/@href"):
                pageNumber = int(jslinkSel.re("pageNumber:\"(\\d+)\"")[0])
                pageSize = int(jslinkSel.re("pageSize:\"(\\d+)\"")[0])
                link = re.sub(r"productBeginIndex:\d+", "productBeginIndex:%d" % ((pageNumber-1) * pageSize), baseUrl)
                pageLinks.add( link )
        return pageLinks

    def parseProductDetails(self, response):
        """
        Parse page with Product key-values
        @type response: TextResponse
        @param response Original HTTP Response
        """
        pass

