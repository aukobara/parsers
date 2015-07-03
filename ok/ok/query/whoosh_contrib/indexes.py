# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

from collections import namedtuple
import logging

from ok.query.whoosh_contrib import find_products, find_brands

log = logging.getLogger(__name__)

"""  INDEXES DECLARATION AND CONFIGURATION  """

INDEX_PRODUCTS = find_products.INDEX_NAME
INDEX_BRANDS = find_brands.INDEX_NAME

IndexDef = namedtuple('_index_def', 'schema feeder checksum queries')
index_def_dict = {INDEX_PRODUCTS: IndexDef(find_products.SCHEMA, find_products.feeder, find_products.data_checksum, [find_products.FindProductsQuery]),
                  INDEX_BRANDS: IndexDef(find_brands.SCHEMA, find_brands.feeder, None, [find_brands.FindBrandsQuery])}
indexes = {}
"""@type: dict of (str, whoosh.index.Index)"""

""""""""""""""""""""""""""""""""""""""""""""""""

def new_searcher(index_name, **kwargs):
    """@rtype: whoosh.searching.Searcher"""
    ix = init_index(one_index=index_name)
    return ix.searcher(**kwargs)

def inject_searcher_factory():
    # Inject searcher_factory to Query clazz
    for index_name, index_def in index_def_dict.items():
        for queryClazz in index_def.queries or []:
            if hasattr(queryClazz, 'searcher_factory'):
                if getattr(queryClazz, 'searcher_factory', None) is not None:
                    log.warn("searcher_factory is already set to query '%s'. Injection overwrites old factory" % queryClazz)
                setattr(queryClazz, 'searcher_factory', staticmethod(new_searcher))
                log.debug(r"Query class %r updated with searcher_factory by %s:%s" % (queryClazz, __name__, new_searcher.__name__))
            else:
                log.debug(r"Query class %r has no searcher_factory attribute and, thus, will have to use client's searchers only" % queryClazz)

inject_searcher_factory()

def init_index(storage=None, index_dir=None, readonly=True, one_index=None):
    """
    @param whoosh.filedb.filestore.Storage|None storage: whoosh storage. If none, storage is treated as FileStorage with dir in index_dir
    @param unicode|None index_dir: if not None use as FileStorage dir, otherwise default dir is used ('out/_whoosh_idx') related to current dir (os.cwd)
    @rtype whoosh.index.FileIndex|dict of (unicode, whoosh.index.FileIndex)
    """

    assert not one_index or one_index in index_def_dict
    if (one_index and indexes.get(one_index)) or (not one_index and indexes):
        return dict(indexes) if not one_index else indexes[one_index]

    original_storage = storage
    if storage is None:
        import ok.settings
        idx_path = ok.settings.ensure_project_path(index_dir or 'out/_whoosh_idx', mkdirs=True)
        from whoosh.filedb.filestore import FileStorage
        storage = FileStorage(idx_path, readonly=readonly)

    res_indexes = {}

    selected_index_def = index_def_dict if not one_index else {one_index: index_def_dict[one_index]}
    for index_name, index_def in selected_index_def.items():
        ok_meta_index_name = '%s_ok_meta' % index_name

        ix = None
        if storage.index_exists(indexname=index_name):
            # Check index is consistent with data and schema
            ix = storage.open_index(indexname=index_name)
            log.info("Open '%s' index from '%s': %d documents" % (index_name, storage, ix.doc_count()))
            assert ix.schema
            if ix.schema != index_def.schema:
                log.info("Schema was changed for index '%s' in '%s' - have to recreate index" % (index_name, storage))
                ix = None
            else:
                if storage.file_exists(ok_meta_index_name):
                    # Verify data checksum
                    if index_def.checksum:
                        required_checksum = index_def.checksum()
                        with storage.open_file(ok_meta_index_name) as metadata_file:
                            indexed_data_checksum = metadata_file.read_long()
                        if required_checksum != indexed_data_checksum:
                            log.info("Checksum of indexed data in index '%s' differs from required - have to recreate index" % index_name)
                            ix = None
                elif index_def.checksum:
                    log.info("Checksum defined but existing index '%s' does not keep it - have to recreate index" % index_name)
                    ix = None

        if not ix:
            log.info("Index '%s' does not exist (or expired) in '%s'. Try to create and feed" % (index_name, storage))
            if readonly and original_storage is None:
                # Readonly mode but index is expired and need to be refreshed
                # As far as storage object was created in this method we can recreate it with writable permissions for index refresh
                from whoosh.filedb.filestore import FileStorage
                writable_storage = FileStorage(storage.folder, readonly=False)
            else:
                # If storage is passed by caller let them check read-write permissions by themselves
                writable_storage = storage

            ix = writable_storage.create_index(index_def.schema, indexname=index_name)
            with ix.writer() as w:
                data_checksum = index_def.feeder(w)
            log.info("Index '%s' created in '%s'. Fed by %d documents" % (index_name, writable_storage, ix.doc_count()))
            if data_checksum:
                with writable_storage.create_file(ok_meta_index_name) as metadata_file:
                    metadata_file.write_long(data_checksum)

            if ix.storage is not storage:
                # Reopen index with original storage after refresh to ensure all storage attributes are correct
                ix = storage.open_index(indexname=index_name)

        res_indexes[index_name] = ix

    indexes.update(res_indexes)
    return dict(indexes) if not one_index else indexes[one_index]
