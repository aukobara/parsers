# -*- coding: utf-8 -*-

# Scrapy settings for ok project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/en/latest/topics/settings.html
#
from scrapy.logformatter import LogFormatter

BOT_NAME = 'ok'

SPIDER_MODULES = ['ok.spiders']
NEWSPIDER_MODULE = 'ok.spiders'

HTTPCACHE_ENABLED = True

# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = 'ok (+http://www.yourdomain.com)'

LOG_ENCODING = "utf-8"
DUPEFILTER_CLASS = "ok.filters.FragmentsONDupFilter"
LOG_LEVEL = "INFO"

ITEM_PIPELINES = {
    "ok.pipelines.OkPipeline" : 100
}

LOG_FORMATTER = "ok.settings.FixEncodingLogFormatter"

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