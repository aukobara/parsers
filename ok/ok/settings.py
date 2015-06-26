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
        raise IOError("Cannot find base dir specified in settings: %s" % base_dir)

    return base_dir


def ensure_project_path(path_in_project=None, mkdirs=False, is_file=False):
    import os.path as path
    if path_in_project and path.isabs(path_in_project):
        project_path = path_in_project
    else:
        import ok
        src_root = path.abspath(path.join(path.dirname(ok.__file__), '..'))
        if not path_in_project:
            project_path = src_root
            is_file = False  # Overwrite is_file because src is directory anyway
        else:
            project_path = path.abspath(path.join(src_root, path_in_project))

    dir_path, _ = path.split(project_path) if is_file else (project_path, None)
    if not path.exists(dir_path):
        if not mkdirs:
            raise IOError("Cannot find intermediate dirs to path specified: %s" % project_path)
        import os
        # Do not create last name, because it can be a file name. Let's user create it
        os.makedirs(dir_path)

    return project_path
