from scrapy.dupefilter import RFPDupeFilter
from scrapy.utils.request import _fingerprint_cache, canonicalize_url
from scrapy.utils.url import canonicalize_url
import hashlib


class FragmentsONDupFilter(RFPDupeFilter):
    """
    Fragments in URLs must be enabled for dummy JS sites who don't read Google recommendations
    """

    def request_fingerprint(self, request):
        """
        This is a partial copy of scrapy.utils.request.request_fingerprint
        Diff:   1) no headers
                2) pass Fragments=True to canonicalize_url
        """
        cache = _fingerprint_cache.setdefault(request, {})
        if None not in cache:
            fp = hashlib.sha1()
            fp.update(request.method)
            fp.update(canonicalize_url(request.url, keep_fragments=True))
            fp.update(request.body or '')
            cache[None] = fp.hexdigest()
        return cache[None]


