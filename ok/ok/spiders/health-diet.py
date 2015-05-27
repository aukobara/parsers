# -*- coding: utf-8 -*-
import re
from scrapy.log import ERROR, DEBUG
from scrapy.contrib.spiders import CrawlSpider
from scrapy.http.request import Request
from ok.items import ProductItem
from ok.spiders import fix_url


class HDietSpider(CrawlSpider):
    name = "hdiet"
    allowed_domains = ["health-diet.ru"]
    start_urls = ["http://health-diet.ru/base_of_food/index.php"]

    """
    <div class="dop_menu">
        <table><tbody>
            <tr><th>Таблицы калорийности и химический состав продуктов</th></tr>
            <tr><td><table width="80%"><colgroup><col width="15%"><col width="35%"><col width="15%"><col width="35%"></colgroup>
                <tbody>
                    <tr>
                    <td><img width="48" height="48" class="iePNG" src="/images/icon/food_13762.png" title="Алкогольные напитки"> </td>
                    <td><a href="base_of_food/food_13762/index.php" title="Таблица калорийности и химический состав: Алкогольные напитки">Алкогольные напитки</a></td>
                    <td><img width="48" height="48" class="iePNG" src="/images/icon/food_1523.png" title="Вода, соки и безалкогольные напитки"> </td>
                    <td><a href="base_of_food/food_1523/index.php" title="Таблица калорийности и химический состав: Вода, соки и безалкогольные напитки">Вода, соки и безалкогольные напитки</a></td>
                    </tr>
                ...
                </tbody>
            </table></td></tr>
        </tbody></table>
    </div>

    """
    URL_CONTEXT = 'base_of_food/'

    rules = [
        # Rule(link_extractor=LxmlLinkExtractor(allow=URL_CONTEXT),
        #      callback='parse_cat', follow=True)
    ]

    def parse_start_url(self, response):
        """
        @param scrapy.http.response.html.HtmlResponse response: response
        """
        links_a_sel = response.css('div.dop_menu a')
        """@type: scrapy.selector.Selector"""
        for href, text in ((a_sel.xpath('@href').extract()[0], a_sel.xpath('text()').extract()) for a_sel in links_a_sel):
            if self.URL_CONTEXT in href:
                cat_url = fix_url(href, response)
                yield Request(cat_url, callback=self.parse_cat, meta={'cat_title': ' '.join(t.strip() for t in text) })
        return

    def parse_cat(self, response):
        """
        @param scrapy.http.response.html.HtmlResponse response: response
        <div id="mainColumn_content">
            <!--СОДЕРЖАНИЕ-->
            <h3>Мясо, птица и мясные продукты. Таблица калорийности продуктов питания.</h3>
            <p>...</p> <p>...</p>
            <h4>Колбасные изделия</h4>
            <table class="content" cellspacing="0" cellpadding="0">
                <colgroup><col width="40%"><col width="15%"><col width="15%"><col width="15%"><col width="15%"></colgroup>
                <tbody>
                    <tr>
                        <th><img src="/template_2/images/apple.jpg">Продукт</th>
                        <th align="center">Калорийность<br>Ккал</th>
                        <th align="center">Белки<br>гр.</th>
                        <th align="center">Жиры<br>гр.</th>
                        <th align="center">Углеводы<br>гр.</th>
                    </tr>
                    <tr>
                        <td class="prod"><a href="base_of_food/sostav/541.php" title="Химический состав продукта: Буженина">Буженина</a></td>
                        <td class="prod">510</td>
                        <td class="prod">15</td>
                        <td class="prod">50</td>
                        <td class="prod">0</td>
                    </tr>
                    ...
                </tbody>
            </table>
            <h4>Косервы мясные</h4>
            <table class="content" cellspacing="0" cellpadding="0">
            ...
            </table>
            <br>
            <div class="find">.../div>
        </div>
        """
        cat_title = response.meta['cat_title']
        self.log("Top cat processing %s" % cat_title, DEBUG)
        top_table_s = response.css('div#mainColumn_content')
        """@type: scrapy.selector.Selector"""
        for sub_cat_table_s in top_table_s.css("table.content"):
            prev_s = sub_cat_table_s.xpath('preceding-sibling::*')
            """@type: list[scrapy.selector.Selector]"""
            sub_cat_title = None
            if prev_s and prev_s[-1].xpath("name()").extract()[0] == 'h4':
                sub_cat_title = prev_s[-1].xpath("string(.)").extract()[0].strip()
            self.log("Sub cat: %s" % sub_cat_title, DEBUG)
            headers = []
            for th_s in sub_cat_table_s.xpath('.//tr/th'):
                headers.append(' '.join(s.strip() for s in th_s.xpath('.//text()').extract()))
            for tr_s in sub_cat_table_s.xpath('.//tr'):
                item = dict()
                for i, td_s in enumerate(tr_s.xpath('./td')):
                    value = ' '.join(s.strip() for s in td_s.xpath('.//text()').extract())
                    item[headers[i]] = value
                    href = td_s.xpath('.//a/@href').extract()
                    if href and '/sostav/' in href[0]:
                        item['crawllink'] = fix_url(href[0], response)
                        m = re.search('/(\d+)\.php', href[0])
                        if m:
                            item['id'] = m.group(1)

                if item:
                    details = {h: item[h] for h in headers}
                    details['top_cat'] = cat_title
                    if sub_cat_title:
                        details['sub_cat'] = sub_cat_title
                    product_item = ProductItem( id=item['id'],
                                                name=item[u'Продукт'],
                                                crawllink=item['crawllink'],
                                                details=details)
                    if not product_item['id']:
                        self.log('Product id was not detected:\r\noriginal: %s\r\nProductItem: %s' % (item, product_item), ERROR)
                    yield product_item
        return