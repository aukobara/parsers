# -*- coding: utf-8 -*-

"""
Basic text processing utils
"""
import os
import re
from sys import argv
from ok.settings import DICT_BASELINE_DEFAULT_DIR


def cleanup_token_str(s, ext_symbols=None):
    """
    Cleanup one-line string from non-label symbols - colon, quotes, periods etc
    Replace multi-spaces to single space. Strip
    @param unicode s: one-line string
    @param list[unicode] ext_symbols: list of additional symbols to clean
    @rtype: unicode
    """
    ext = '|'.join(ext_symbols) if ext_symbols else None
    return re.sub(u'(?:\s|"|,|\.|«|»|“|”|\(|\)|\?|\+' + ('|' + ext if ext else '') + ')+', u' ', s).strip()


def isenglish(s):
    try:
        (s.encode("utf-8") if isinstance(s, unicode) else s).decode('ascii')
        return True
    except UnicodeDecodeError:
        return False


def isrussian(s):
    if isenglish(s):
        return False
    try:
        (s.encode("utf-8") if isinstance(s, unicode) else s).decode('cp1251')
        return True
    except UnicodeDecodeError:
        return False


def add_string_combinations(patterns, *repl):
    # Collect all possible pattern combinations
    result = list(patterns)
    p_modified = True
    while p_modified:
        p_modified = False
        for p in result[:]:
            p1 = p
            for r in repl:
                p1 = p.replace(*r)
                if p1 != p and p1 not in result:
                    break
            if p1 not in result:
                result.append(p1)
                p_modified = True
    return result


def remove_nbsp(s):
    return None if s is None else s.replace(u'\u00a0', ' ') if isinstance(s, unicode) else s.replace('\xa0', ' ')


def main_options(opts=argv):
    """
    @param list[str] opts: command line tokens starts with script name
    @return: config
    @rtype: dict of (str,str)
    """
    opts = opts[:]
    baseline_dir = None
    prodcsvname = None
    toprint = None
    cat_csvname = None
    brands_in_csvname = None
    brands_out_csvname = None  # Don't save brands by default
    while len(opts) > 1:
        opt = opts.pop(1)
        if opt == "-p" and len(opts) > 1:
            toprint = opts.pop(1)
        elif opt == "-c" and len(opts) > 1:
            cat_csvname = opts.pop(1)
        elif opt == "-in-brands-csv" and len(opts) > 1:
            brands_in_csvname = opts.pop(1)
        elif opt == "-out-brands-csv" and len(opts) > 1:
            brands_out_csvname = opts.pop(1)
        elif opt == "-base-dir" and len(opts) > 1:
            baseline_dir = opts.pop(1)
        elif not opt.startswith('-') and not prodcsvname:
            prodcsvname = opt
        else:
            raise Exception("Unknown options")
    # Defaults
    toprint = toprint or "producttypes"
    baseline_dir = baseline_dir or DICT_BASELINE_DEFAULT_DIR
    cat_csvname = cat_csvname or os.path.abspath(os.path.join(baseline_dir, 'cats.csv'))
    brands_in_csvname = brands_in_csvname or os.path.abspath(os.path.join(baseline_dir, 'brands.csv'))
    prodcsvname = prodcsvname or os.path.abspath(os.path.join(baseline_dir, 'products_raw.csv'))
    return dict(
        toprint=toprint,
        prodcsvname=prodcsvname,
        cat_csvname=cat_csvname,
        brands_in_csvname=brands_in_csvname,
        brands_out_csvname=brands_out_csvname
    )