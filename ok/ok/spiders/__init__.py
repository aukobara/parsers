# This package will contain the spiders of your Scrapy project
#
# Please refer to the documentation for information on how to create and manage
# your spiders.
from urlparse import urlparse, urljoin


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
