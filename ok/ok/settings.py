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

LOG_ENCODING = "utf-8"
DUPEFILTER_CLASS = "ok.filters.FragmentsONDupFilter"
LOG_LEVEL = "INFO"

ITEM_PIPELINES = {
    "ok.pipelines.OkPipeline" : 100
}

LOG_FORMATTER = "ok.FixEncodingLogFormatter"

DICT_BASELINE_DEFAULT_DIR = 'resources/data/ok/baseline150609'

def ensure_baseline_dir():
    from os.path import abspath, isdir, join, dirname
    base_dir = abspath(DICT_BASELINE_DEFAULT_DIR)
    if not isdir(base_dir):
        # Try relative path from source folder
        import ok
        src_root = abspath(join(dirname(ok.__file__), '..'))
        _base_dir = abspath(join(src_root, DICT_BASELINE_DEFAULT_DIR))
        if isdir(_base_dir):
            base_dir = _base_dir
    if not isdir(base_dir):
        raise Exception("Cannot find base dir specified in settings: %s" % base_dir)

    return base_dir