# coding: utf-8
from urlparse import urlunparse
import scrapy
from scrapy.contrib.exporter import CsvItemExporter
from scrapy.http.request.form import FormRequest
from scrapy.http.response.text import TextResponse
from scrapy.selector.unified import Selector
from scrapy.log import ERROR
from scrapy.utils.url import parse_url
from ok.items import CatItem, ProductItem, ROOT_CAT_ITEM
import re
from ok.settings import FixEncodingLogFormatter

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

    cats = dict()
    """ @type cats: dict of (unicode, ok.items.CatItem) """
    stop_cats = [
        "15075", "16614", "15070", "16622", "16629", "16053", "15093", "16068", "24577", "15055", "26090", "26092", "15058", "16608"  # top non-product cats
    ]

    def __init__(self):
        super(RootCatSpider, self).__init__()
        self.cats[ROOT_CAT_ITEM["id"]] = ROOT_CAT_ITEM
        # self.download_delay = 1/2

    def closed(self, reason):
        with open("out/cats.csv", "wb") as file:
            file.truncate()
            fields = CatItem.fields.keys()
            exporter = CsvItemExporter(file, fields_to_export=[f for f in fields if f not in ("stop")])
            exporter.start_exporting()
            [exporter.export_item(cat) for cat in self.cats.itervalues() if not cat.get("stop", False)]
            exporter.finish_exporting()

    def parse(self, response):
        """
        @type response: TextResponse
        @param response
        """
        catItems = self.parseCats(response)
        for item in catItems:
            yield item
        # This should be after cat parsing because it can add some virtual catItemId to response.meta
        catItemId = response.meta.get("catItemId")

        pageAjaxReqs = self.parseProductListPaging(response)
        for req in pageAjaxReqs:
            yield req

        prodContSel = response.css("div.product_listing_container")
        for prodSel in prodContSel.css("div.product"):
            item = self.parseProductThumbnail(prodSel)
            if item:
                # add item's id to current category item
                if catItemId:
                    currentCatItem = self.cats[catItemId]
                    currentCatItem["products"] = [] if not currentCatItem["products"] else currentCatItem["products"]
                    currentCatItem["products"].append(item["id"])
                    currentCatItem["productCount"] = len(currentCatItem["products"])

                # yield item
                if item["crawllink"]:
                    pdpRequest = scrapy.Request(item["crawllink"], callback=self.parseProductDetails)
                    pdpRequest.meta["prodItem"] = item
                    # yield pdpRequest
                else:
                    self.log("Link is empty or unparsed to PDP on page %r for product %r" %
                               (response.url, item["name"]), level=ERROR)
                    yield item  # return broken uncompleted product

    def parseCats(self, response):
        """
        Parse one level of sub-categories only. Deep cats will be parsed recursively
        @type response: TextResponse
        @rtype: list[scrapy.Request]
        """
        currentCatItemId = response.meta.get("catItemId")
        childCatSel = response.css('div#categoryNavigationMenu > ul > li > a.menuLink')
        if not childCatSel:
            # home page? all dep menu. NOTE: homePageMenu div is filled by js after load. Empty in response body.
            # Use fluid header menu for top cats
            if response.css('div#homePageMenu'):
                childCatSel = response.css('ul#allDepartmentsMenu > li > a.menuLink')
                if currentCatItemId is None:
                    currentCatItemId = ROOT_CAT_ITEM["id"]  # mimic ROOT (HomePage) cat
                    response.meta["catItemId"] = currentCatItemId
        if not currentCatItemId:
            # TODO - determine parent cat by current page if crawling not from TOP
            self.log("Parent cat 's not found for category page: %s" % response.url, scrapy.log.WARNING)
            currentCatItemId = ROOT_CAT_ITEM["id"]  # mimic ROOT (HomePage) cat
            response.meta["catItemId"] = currentCatItemId

        items = []
        # Iterate children
        for catSel in childCatSel:
            childItem = self.parseCatLink(catSel, self.cats[currentCatItemId])

            if not childItem["id"] or self.cats.get(childItem["id"]):
                self.log("Category [id: %d, title: %s] with duplicated or empty ID on page %s" % (childItem["id"], childItem["title"], response.url),
                         scrapy.log.ERROR)

            elif childItem["crawllink"]:
                self.cats[childItem["id"]] = childItem

                if not self.underStopCat(childItem):
                    subcatReq = scrapy.Request(childItem["crawllink"], callback=self.parse,
                                               meta = { "catItemId": childItem["id"] }, priority=2)
                    items += [subcatReq]
                else:
                    self.log("Category [id: %s, title: %s] is under stop list. Skipped" % (childItem["id"], childItem["title"]),
                             scrapy.log.INFO)
                    childItem["stop"] = True

            else:
                self.log("Category [title: %s] with broken or empty link on page %s" % (childItem["title"], response.url),
                         scrapy.log.WARNING)
        return items

    def parseCatLink(self, selA, parentItem):
        """
        @param Selector selA: Selector of <a> with category link
        @param CatItem parentItem: category Item which produces children or None if child is Top Cat
        @rtype: CatItem
        """
        item = CatItem()
        item["id"] = selA.xpath("@id").re('(\d+)')[-1]
        item["title"] = selA.xpath("text()").extract()[0].strip()
        item["crawllink"] = selA.xpath("@href").extract()[0]
        item["level"] = int( parentItem["level"] ) + 1
        item["parentId"] = parentItem["id"]
        if parentItem.get("pathTitles", None):
            item["pathTitles"] = [parentItem["title"]] + parentItem["pathTitles"]
        else:
            item["pathTitles"] = [parentItem["title"]]
        item["productCount"] = 0
        item["products"] = []
        return item

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
                    req = FormRequest(baseUrl, formdata=sorted(pagingParams.iteritems()), meta=response.meta, priority=1)
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
        item ["id"] = self._parseEntitledItem(selP.xpath(".."))  # select parent <li> element
        # NOTE. Title attribute may have a bug if name contains quotes (") - it will be split by first quote
        item ["name"] = selP.xpath(".//div[@class='product_name']/a/@title").extract()[0].strip()
        item ["crawllink"] = selP.xpath(".//div[@class='product_name']/a/@href").extract()[0]
        item ["imgUrl"] = selP.xpath(".//div[@class='image']//img/@src").extract()[0]
        item ["weight"] = ' '.join([txt.strip() for txt in selP.xpath(".//div[@class='product_weight']/span/text()").extract()])
        selPrice = selP.css("span.product_price span.price.label")
        item ["price"] = selPrice.xpath("text()").extract()[0].strip() if selPrice else None
        return item

    _entitledItem_catentry_id_re = re.compile('"catentry_id"\s+:\s+"(\d+)",')
    def _parseEntitledItem(self, response):
        entItemJsonSel = response.xpath('descendant-or-self::div[starts-with(@id, "entitledItem_")]/text()')
        productId = int(entItemJsonSel.re(self._entitledItem_catentry_id_re)[0])
        return productId

    def parseProductDetails(self, response):
        """
        Parse page with Product key-values. Executed by Spider
        @type response: TextResponse
        @param response Original HTTP Response
        response.meta["prodItem"] contains ProductItem from category grid
        """
        item = response.meta["prodItem"]
        """@type item: ProductItem"""
        productInfoSel = response.css('div.product-info')
        # lookup for entitledSection bottom-up to avoid full document scan
        productId = self._parseEntitledItem(productInfoSel.xpath('ancestor::div/preceding-sibling::div[starts-with(@id, "entitledItem_")]'))
        item ["id"] = productId
        parsedUrl = parse_url(response.url)
        item ["link"] = urlunparse((parsedUrl.scheme, parsedUrl.netloc.lower(), "webapp/wcs/stores/servlet/ProductDisplay", "",
                                "urlRequestType=Base&productId=%d&storeId=10151" % productId, ""))

        # Check product name on PDP and validate with thumbnail
        name = ' '.join(txt.strip() for txt in
                        productInfoSel.css("div.namePartPriceContainer .main_header")
                                .xpath(".//text()").extract() if txt.strip())
        if name != item["name"]:
            self.log("Product[id=%d] name is different on thumbnail and PDP. TB: %s => PDP: %s" % (productId, item["name"], name), scrapy.log.WARNING)
            if name:
                item["name"] = name

        # Check mandatory attributes
        if not item["id"] or not item["name"] or not item["price"]:
            logformatter = self.crawler.logformatter
            dumpItem = item
            if isinstance(logformatter, FixEncodingLogFormatter):
                dumpItem = logformatter.encodeDumpObject(item)
            self.log("Product[id=%d] has empty one of mandatory attributes (id,price,name):\n%r" %(item["id"],dumpItem), scrapy.log.ERROR)

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
            key = " ".join(txt.strip() for txt in tr.xpath("th//text()").extract() if txt.strip())
            value = " ".join(txt.strip() for txt in tr.xpath("td//text()").extract() if txt.strip())
            if key and value:
                details[key] = value
        return details

    def underStopCat(self, childItem):
        """
        Check if next child catItem is in stop_cats list or its descendant
        @param CatItem childItem:
        @rtype: bool
        """
        if childItem["id"] in self.stop_cats:
            # stop current cat?
            return True
        currentId = childItem["parentId"]
        while currentId is not None and currentId not in self.stop_cats:
            currentId = self.cats[currentId].get("parentId")
        return currentId is not None

