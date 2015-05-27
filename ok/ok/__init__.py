from scrapy.logformatter import LogFormatter
from ok.settings import LOG_ENCODING


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