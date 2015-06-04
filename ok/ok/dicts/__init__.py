# -*- coding: utf-8 -*-

"""
Basic text processing utils
"""
from collections import namedtuple
import os
import re
from sys import argv

from ok.settings import ensure_baseline_dir


def cleanup_token_str(s, ext_symbols=None):
    """
    Cleanup one-line string from non-label symbols - colon, quotes, periods etc
    Replace multi-spaces to single space. Strip
    @param unicode s: one-line string
    @param list[unicode] ext_symbols: list of additional symbols to clean
    @rtype: unicode
    """
    ext = u'|'.join(ext_symbols) if ext_symbols else None
    return re.sub(u'(?:\s|"|,|\.|«|»|“|”|\(|\)|\?|\+|:' + (u'|' + ext if ext else u'') + ')+', u' ', s).strip()


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
    return None if s is None else s.replace(u'\u00a0', u' ') if isinstance(s, unicode) else s.replace('\xc2\xa0', ' ')


conf_type = namedtuple('OKConfig', 'toprint baseline_dir prodcsvname cat_csvname '
                       'brands_in_csvname brands_out_csvname '
                       'products_meta_in_csvname products_meta_out_csvname '
                       'product_types_in_json product_types_out_json '
                       'word_forms_dict term_dict')

def main_options(opts=argv):
    """
    @param list[str] opts: command line tokens starts with script name
    @return: config
    @rtype: conf_type
    """
    opts = opts[:]
    baseline_dir = None
    prodcsvname = None
    toprint = None
    cat_csvname = None
    brands_in_csvname = None
    brands_out_csvname = None  # Don't save brands by default
    products_meta_in_csvname = None  # Don't load meta types by default
    products_meta_out_csvname = None  # Don't save meta types by default
    product_types_in_json = None
    product_types_out_json = None  # Don't save product types by default
    word_forms_dict = None
    term_dict = None
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
        elif opt == "-in-products-meta-csv" and len(opts) > 1:
            products_meta_in_csvname = opts.pop(1)
        elif opt == "-out-products-meta-csv" and len(opts) > 1:
            products_meta_out_csvname = opts.pop(1)
        elif opt == "-in-product-types-json" and len(opts) > 1:
            product_types_in_json = opts.pop(1)
        elif opt == "-out-product-types-json" and len(opts) > 1:
            product_types_out_json = opts.pop(1)
        elif opt == "-word-forms-dict" and len(opts) > 1:
            word_forms_dict = opts.pop(1)
        elif opt == "-term-dict" and len(opts) > 1:
            term_dict = opts.pop(1)
        elif opt == "-base-dir" and len(opts) > 1:
            baseline_dir = opts.pop(1)
        elif not opt.startswith('-') and not prodcsvname:
            prodcsvname = opt
        else:
            raise Exception((u"Unknown options: %s" % opt).encode("utf-8"))
    # Defaults
    toprint = toprint or "producttypes"
    baseline_dir = baseline_dir or ensure_baseline_dir()
    cat_csvname = cat_csvname or os.path.abspath(os.path.join(baseline_dir, 'cats.csv'))
    brands_in_csvname = brands_in_csvname or os.path.abspath(os.path.join(baseline_dir, 'brands.csv'))
    prodcsvname = prodcsvname or os.path.abspath(os.path.join(baseline_dir, 'products_raw.csv'))
    # products_meta_in_csvname = products_meta_in_csvname or os.path.abspath(os.path.join(baseline_dir, 'products_meta.csv'))
    product_types_in_json = product_types_in_json or os.path.abspath(os.path.join(baseline_dir, 'product_types.json'))
    word_forms_dict = word_forms_dict or os.path.abspath(os.path.join(baseline_dir, 'word_forms_dict.txt'))
    term_dict = term_dict or os.path.abspath(os.path.join(baseline_dir, 'term_dict.dawg'))
    return conf_type(
        toprint=toprint,
        baseline_dir=baseline_dir,
        prodcsvname=prodcsvname,
        cat_csvname=cat_csvname,
        brands_in_csvname=brands_in_csvname,
        brands_out_csvname=brands_out_csvname,
        products_meta_in_csvname=products_meta_in_csvname,
        products_meta_out_csvname=products_meta_out_csvname,
        product_types_in_json=product_types_in_json,
        product_types_out_json=product_types_out_json,
        word_forms_dict=word_forms_dict,
        term_dict=term_dict,
    )




