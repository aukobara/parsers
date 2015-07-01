# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import
import logging
from time import time

from flask import Flask
from flask_cache import Cache
from werkzeug.contrib.cache import SimpleCache

app = Flask(__name__)
app.config.from_object('config')

loggers = [logging.getLogger('ok'), logging.getLogger('app')]
lh = logging.StreamHandler()
lh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
for logger in loggers:
    logger.setLevel(logging.DEBUG)
    logger.addHandler(lh)

class DummyCache(SimpleCache):

    def __init__(self, _, config, args, kwargs):
        kwargs.update(dict(threshold=config['CACHE_THRESHOLD'], default_timeout=86400))
        super(DummyCache, self).__init__(*args, **kwargs)

    def get(self, key):
        try:
            expires, value = self._cache[key]
            if expires > time():
                return value
            else:
                print("Expired key evicted from cache: %s" % key)
        except KeyError:
            return None

    def add(self, key, value, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        self._prune()
        item = (time() + timeout, value)
        if key in self._cache:
            return False
        self._cache.setdefault(key, item)
        return True

    def set(self, key, value, timeout=None):
        if timeout is None:
            timeout = self.default_timeout
        self._prune()
        self._cache[key] = (time() + timeout, value)
        return True

cache = Cache(app, config={'CACHE_TYPE': 'app.DummyCache'})

def get_config(base_dir=None):
    import ok.dicts

    config = ok.dicts.main_options([] if not base_dir else ['', '-base-dir', base_dir])
    import os.path

    product_types_in_json_bin = config.product_types_in_json
    if '.bin' not in product_types_in_json_bin:
        product_types_in_json_bin = '%s.bin%s' % os.path.splitext(product_types_in_json_bin)
        if os.path.isfile(product_types_in_json_bin):
            config = config._replace(product_types_in_json=product_types_in_json_bin)

    config = config._replace(products_meta_in_csvname=os.path.join(config.baseline_dir, 'products_meta.csv'))
    return config

data_config = get_config()

from app.search.views import mod as search_module
app.register_blueprint(search_module)
