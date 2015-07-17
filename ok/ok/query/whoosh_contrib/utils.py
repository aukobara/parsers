# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

from whoosh import searching, query


def text_data_file_checksum(filename):
    """@rtype: long"""
    from whoosh.filedb.structfile import ChecksumFile

    with open(filename) as data_file:
        cf = ChecksumFile(data_file)
        all(cf)  # Iterate through all lines to calculate checksum
        return cf.checksum()


class ResultsWrapper(searching.Results):
    """
    Allows override original whoosh Results object.
    Main goal to replace or extend Hit objects
    """

    def __init__(self, translate, *args, **kwargs):
        super(ResultsWrapper, self).__init__(*args, **kwargs)
        assert translate is None or callable(translate)
        self.translate = translate

    def __iter__(self):
        wrap_hit = self.wrap_hit
        hits_iter = super(ResultsWrapper, self).__iter__()
        for hit in hits_iter:
            yield wrap_hit(hit)

    def __getitem__(self, n):
        hit = super(ResultsWrapper, self).__getitem__(n)
        wrap_hit = self.wrap_hit
        if isinstance(hit, list):
            return [wrap_hit(hit_item) for hit_item in hit]
        return wrap_hit(hit)

    def wrap_hit(self, hit):
        translate = self.translate
        return hit if translate is None or hit is None else translate(hit)


def hit_stored_fields_wrapper(stored_fields):

    def translate_hit(hit):
        """@param whoosh.searching.Hit hit: original new Hit instance"""
        docnum = hit.docnum
        fields = stored_fields.get(docnum)
        hit._fields = fields
        return hit

    return translate_hit


class ResultsPreCachedStoredFields(ResultsWrapper):
    def __init__(self, stored_fields, *args, **kwargs):
        translate = hit_stored_fields_wrapper(stored_fields)
        super(ResultsPreCachedStoredFields, self).__init__(translate, *args, **kwargs)


def and_or_query(sub_queries, And=query.And, Or=query.Or, boost=1.0):
    if not sub_queries:
        return tuple()
    if len(sub_queries) == 1:
        one_query = sub_queries[0]
        if boost != 1.0:
            one_query.boost *= boost
        return one_query,
    if And is not None and Or is not None:
        return And(sub_queries, boost=boost), Or(sub_queries, boost=boost)
    if And is not None:
        return And(sub_queries, boost=boost),
    if Or is not None:
        return Or(sub_queries, boost=boost),
    raise AssertionError("Either And or Or operator must be defined")
