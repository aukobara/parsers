# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function


def text_data_file_checksum(filename):
    """@rtype: long"""
    from whoosh.filedb.structfile import ChecksumFile

    with open(filename) as data_file:
        cf = ChecksumFile(data_file)
        all(cf)  # Iterate through all lines to calculate checksum
        return cf.checksum()