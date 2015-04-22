# -*- coding: utf-8 -*-

# Scrapy settings for ok project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/en/latest/topics/settings.html
#

BOT_NAME = 'ok'

SPIDER_MODULES = ['ok.spiders']
NEWSPIDER_MODULE = 'ok.spiders'

HTTPCACHE_ENABLED = True

# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = 'ok (+http://www.yourdomain.com)'

LOG_ENCODING = "cp1251"
DUPEFILTER_CLASS = "ok.filters.FragmentsONDupFilter"
LOG_LEVEL = "INFO"