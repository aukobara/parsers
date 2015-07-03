# This package will contain the spiders of your Scrapy project
#
# Please refer to the documentation for information on how to create and manage
# your spiders.
from urlparse import urlparse, urljoin
from scrapy.logformatter import LogFormatter
from ok.settings import LOG_ENCODING


def fix_url(href, response):
    """
    @param scrapy.http.response.html.HtmlResponse response: response
    """
    url_p = urlparse(href)
    if not url_p.scheme and not href.startswith('/'):
        # Fix relative path
        href = '/' + href
    cat_url = urljoin(response.url, href)
    return cat_url


class FixEncodingLogFormatter(LogFormatter):
    def encodeDumpObject(self, obj):
        """
        @return: unicode
        """
        return ("%r" % obj).decode("unicode-escape").encode(LOG_ENCODING)

    def dropped(self, item, exception, response, spider):
        dropped = super(FixEncodingLogFormatter, self).dropped(item, exception, response, spider)
        """@type dropped: dict of (unicode, unicode)"""
        dropped["item"] = self.encodeDumpObject(dropped["item"])
        return dropped