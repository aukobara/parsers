# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
from collections import namedtuple

import logging
from whoosh.index import exists_in, create_in, open_dir
from ok.settings import ensure_project_path

log = logging.getLogger(__name__)

import find_products
import find_brands

INDEX_PRODUCTS = find_products.INDEX_NAME
INDEX_BRANDS = find_brands.INDEX_NAME

IndexDef = namedtuple('_index_def', 'schema feeder checksum')
index_def_dict = {INDEX_PRODUCTS: IndexDef(find_products.SCHEMA, find_products.feeder, find_products.data_checksum),
                  INDEX_BRANDS: IndexDef(find_brands.SCHEMA, find_brands.feeder, None)}
indexes = {}
"""@type: dict of (str, whoosh.index.Index)"""

def init_index(index_dir=None, readonly=True):
    if indexes:
        return
    idx_path = ensure_project_path(index_dir or 'out/_whoosh_idx', mkdirs=True)
    res_indexes = {}
    for index_name, index_def in index_def_dict.items():
        ok_meta_index_name = '%s_ok_meta' % index_name

        if exists_in(idx_path, indexname=index_name):
            # Check index is consistent with data and schema
            ix = open_dir(idx_path, readonly=readonly, indexname=index_name)
            log.info("Open '%s' index from '%s': %d documents" % (index_name, idx_path, ix.doc_count()))
            assert ix.schema
            if ix.schema != index_def.schema:
                log.info("Schema was changed for index '%s' in '%s' - have to recreate index" % (index_name, idx_path))
                ix = None
            else:
                if ix.storage.file_exists(ok_meta_index_name):
                    # Verify data checksum
                    if index_def.checksum:
                        required_checksum = index_def.checksum()
                        with ix.storage.open_file(ok_meta_index_name) as metadata_file:
                            indexed_data_checksum = metadata_file.read_long()
                        if required_checksum != indexed_data_checksum:
                            log.info("Checksum of indexed data in index '%s' differs from required - have to recreate index" % index_name)
                            ix = None
                elif index_def.checksum:
                    log.info("Checksum defined but existing index '%s' does not keep it - have to recreate index" % index_name)
                    ix = None

        if not ix:
            log.info("Index '%s' does not exist (or expired) in '%s'. Try to create and feed" % (index_name, idx_path))
            ix = create_in(idx_path, index_def.schema, indexname=index_name)
            with ix.writer() as w:
                data_checksum = index_def.feeder(w)
            log.info("Index '%s' created in '%s'. Fed by %d documents" % (index_name, idx_path, ix.doc_count()))
            if data_checksum:
                with ix.storage.create_file(ok_meta_index_name) as metadata_file:
                    metadata_file.write_long(data_checksum)

        res_indexes[index_name] = ix

    indexes.update(res_indexes)

def text_data_file_checksum(filename):
    """@rtype: long"""
    from whoosh.filedb.structfile import ChecksumFile

    with open(filename) as data_file:
        cf = ChecksumFile(data_file)
        all(cf)  # Iterate through all lines to calculate checksum
        return cf.checksum()
