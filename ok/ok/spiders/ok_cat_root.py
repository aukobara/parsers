# coding: cp1251
from urlparse import urlunparse
import scrapy
from scrapy.http.request.form import FormRequest
from scrapy.http.response.text import TextResponse
from scrapy.log import ERROR
from scrapy.utils.url import parse_url
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
    # start_urls = ["http://www.okeydostavka.ru/msk/%D1%81%D0%BA%D0%B8%D0%B4%D0%BA%D0%B8",
    #               "http://www.okeydostavka.ru/msk/%D0%BC%D0%BE%D0%BB%D0%BE%D1%87%D0%BD%D1%8B%D0%B5-%D0%BF%D1%80%D0%BE%D0%B4%D1%83%D0%BA%D1%82%D1%8B--%D1%81%D1%8B%D1%80%D1%8B--%D1%8F%D0%B9%D1%86%D0%BE"]

    def __init__(self):
        super(RootCatSpider, self).__init__()
        with open("catlog.txt", "w") as f:
            f.truncate()
            self.download_delay = 1/2

    def extractA(self, selA):
        text = selA.xpath("text()").extract()[0].strip()
        url = selA.xpath("@href").extract()[0]
        return url, text

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

        pageAjaxReqs = self.parseProductListPaging(response)
        for req in pageAjaxReqs:
            yield req

        prodContSel = response.xpath("//div[@class='product_listing_container']")
        for prodSel in prodContSel.css("div.product"):
            item = self.parseProductThumbnail(prodSel)
            if item:
                # yield item
                if item["crawllink"]:
                    pdpRequest = scrapy.Request(item["crawllink"], callback=self.parseProductDetails)
                    pdpRequest.meta["prodItem"] = item
                    yield pdpRequest
                else:
                    self.log("Link is empty or unparsed to PDP on page %r for product %r" %
                               (response.url, item["name"]), level=ERROR)
                    yield item  # return broken uncompleted product

    def parseProductListPaging(self, response):
        """
        Parse paging links on Product Grid pages

        <div id="pageControlMenu_6_-1011_3074457345618259713" class="pageControlMenu" data-dojo-attach-point="pageControlMenu" data-parent="header">
            <div class="pageControl number">
                <a class="active selected" href="#" role="button" aria-disabled="true" aria-label="Перейти к странице 1" tabindex="-1">1</a>
                <a class="hoverover" role="button" href='javascript:dojo.publish("showResultsForPageNumber",
                    [{pageNumber:"2",pageSize:"72", linkId:"WC_SearchBasedNavigationResults_pagination_link_2_categoryResults"}])'
                    id="WC_SearchBasedNavigationResults_pagination_link_2_categoryResults" aria-label="Перейти к странице 2" title="Перейти к странице 2">2</a>

        Base POST form url for refresh data via AJAX
        <script>
		dojo.addOnLoad(function(){
			SearchBasedNavigationDisplayJS.init('_6_-1011_3074457345618259713',
			'http://www.okeydostavka.ru/webapp/wcs/stores/servlet/ProductListingView?searchType=1000&filterTerm=&langId=-20&advancedSearch=&sType=SimpleSearch&gridPosition=&metaData=&manufacturer=&custom_view=true&ajaxStoreImageDir=%2Fwcsstore%2FOKMarketSAS%2F&resultCatEntryType=&catalogId=10551&searchTerm=&resultsPerPage=72&emsName=&facet=&categoryId=16106&storeId=10151&disableProductCompare=true&ddkey=ProductListingView_6_-1011_3074457345618259713&filterFacet=');
		});
	    </script>

        Current orderBy: <input type="hidden" name="orderBy" data-dojo-attach-point="valueNode" value="2" aria-hidden="true">
        Link format: {cat-url}#facet:&productBeginIndex:72&orderBy:2&pageView:grid&minPrice:&maxPrice:&pageSize:&
        """
        if response.meta.get("skip_paging", False):
            return []
        pageAjaxReqs = []
        pageNumbers = set()
        pageMenuSel = response.xpath("//div[@class='pageControlMenu']")
        if pageMenuSel:
            initScript = response.xpath("//script[contains(text(), 'SearchBasedNavigationDisplayJS.init(')]/text()").extract()[0]
            baseUrl = re.search("SearchBasedNavigationDisplayJS\.init\('[^']*',\s*'([^']*)'\)", initScript, re.MULTILINE).group(1)

            orderBySel = response.xpath("//div[@class='orderByDropdown selectWrapper']//option[@selected]/@value").extract()
            orderBy = orderBySel[0] if orderBySel else ""

            for jslinkSel in pageMenuSel.xpath(".//a[contains(@href, 'pageNumber')]/@href"):
                pageNumber = int(jslinkSel.re("pageNumber:\"(\\d+)\"")[0])
                if pageNumber not in pageNumbers:
                    pageSize = int(jslinkSel.re("pageSize:\"(\\d+)\"")[0])
                    beginIndex = (pageNumber - 1) * pageSize

                    searchParams = {}
                    for inpSel in response.xpath("//form[@name='CatalogSearchForm']//input[@type='hidden']"):
                        nameSel = inpSel.xpath("@name").extract()
                        valueSel = inpSel.xpath("@value").extract()
                        if nameSel and valueSel:
                            searchParams[ nameSel[0] ] = valueSel[0]
                    pagingParams = {
                        "contentBeginIndex": "0",
                        "productBeginIndex": str( beginIndex ),
                        "beginIndex": str( beginIndex ),
                        "orderBy": orderBy or "2",
                        "facetId:": "",
                        "pageView": "grid",
                        "resultType": "products",
                        "orderByContent": "",
                        "searchTerm": "",
                        "facet": "",
                        "facetLimit": "",
                        "pageSize": "",
                        "storeId": searchParams.get("storeId", "10151"),
                        "catalogId": searchParams.get("catalogId", "10551"),
                        "langId": searchParams.get("langId", "-20"),
                        "objectId": "_6_-1011_3074457345618259713",
                        "requesttype": "ajax"
                    }
                    req = FormRequest(baseUrl, formdata=sorted(pagingParams.iteritems()))
                    req.meta["skip_paging"] = True # avoid recursive paging because of broken baseURL in ajax responses
                    pageAjaxReqs.append( req )
        return pageAjaxReqs

    def parseProductThumbnail(self, selP):
        """
        Extract ProductItem from category product's grid's topmost <div class='product...>
        @param selP: Selector to <div class='product...'>
        @type selP: TextResponse
        @return: ProductItem
        Sample at ./product_item.xml
        """
        if not selP.xpath(".//div[@class='product_name']/a/text()").extract():
            return None

        item = ProductItem()
        item ["name"] = selP.xpath(".//div[@class='product_name']/a/@title").extract()[0].strip()
        item ["crawllink"] = selP.xpath(".//div[@class='product_name']/a/@href").extract()[0]
        item ["imgUrl"] = selP.xpath(".//div[@class='image']//img/@src").extract()[0]
        item ["weight"] = ' '.join([txt.strip() for txt in selP.xpath(".//div[@class='product_weight']/span/text()").extract()])
        selPrice = selP.css("span.product_price span.price.label")
        item ["price"] = selPrice.xpath("text()").extract()[0].strip() if selPrice else None
        return item

    def parseProductDetails(self, response):
        """
        Parse page with Product key-values. Executed by Spider
        @type response: TextResponse
        @param response Original HTTP Response
        response.meta["prodItem"] contains ProductItem from category grid
        """
        item = response.meta["prodItem"]
        """@type item: ProductItem"""
        entItemJsonSel = response.xpath("//div[starts-with(@id, 'entitledItem_')]/text()")
        productId = int( entItemJsonSel.re("\"catentry_id\"\s+:\s+\"(\d+)\",")[0] )
        item ["id"] = productId
        parsedUrl = parse_url(response.url)
        item ["link"] = urlunparse((parsedUrl.scheme, parsedUrl.netloc.lower(), "webapp/wcs/stores/servlet/ProductDisplay", "",
                                "urlRequestType=Base&productId=%d&storeId=10151" % productId, ""))

        details = self.parsePDPkeyvalues(response)
        item ["details"] = details
        yield item

    def parsePDPkeyvalues(self, response):
        """
        @type response: TextResponse
        @return: dict
        """
        trSelList = response.css("div.product-characteristics tr,div.product-desc tr")
        details = {}
        for tr in trSelList:
            key = " ".join(txt.strip() for txt in tr.xpath("th//text()").extract())
            value = " ".join(txt.strip() for txt in tr.xpath("td//text()").extract())
            details[key] = value
        return details

