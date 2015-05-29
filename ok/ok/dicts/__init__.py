# -*- coding: utf-8 -*-

"""
Basic text processing utils
"""
from collections import namedtuple
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
    ext = u'|'.join(ext_symbols) if ext_symbols else None
    return re.sub(u'(?:\s|"|,|\.|«|»|“|”|\(|\)|\?|\+|:' + (u'|' + ext if ext else u'') + ')+', u' ', s).strip()


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
    return None if s is None else s.replace(u'\u00a0', u' ') if isinstance(s, unicode) else s.replace('\xc2\xa0', ' ')


conf_type = namedtuple('OKConfig', 'toprint baseline_dir prodcsvname cat_csvname '
                       'brands_in_csvname brands_out_csvname '
                       'products_meta_in_csvname products_meta_out_csvname '
                       'product_types_in_json product_types_out_json')

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
        elif opt == "-base-dir" and len(opts) > 1:
            baseline_dir = opts.pop(1)
        elif not opt.startswith('-') and not prodcsvname:
            prodcsvname = opt
        else:
            raise Exception((u"Unknown options: %s" % opt).encode("utf-8"))
    # Defaults
    toprint = toprint or "producttypes"
    baseline_dir = baseline_dir or DICT_BASELINE_DEFAULT_DIR
    cat_csvname = cat_csvname or os.path.abspath(os.path.join(baseline_dir, 'cats.csv'))
    brands_in_csvname = brands_in_csvname or os.path.abspath(os.path.join(baseline_dir, 'brands.csv'))
    prodcsvname = prodcsvname or os.path.abspath(os.path.join(baseline_dir, 'products_raw.csv'))
    # products_meta_in_csvname = products_meta_in_csvname or os.path.abspath(os.path.join(baseline_dir, 'products_meta.csv'))
    product_types_in_json = product_types_in_json or os.path.abspath(os.path.join(baseline_dir, 'product_types.json'))
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
    )

__pymorph_analyzer = None
"""@type: pymorphy2.MorphAnalyzer"""
def get_word_normal_form(word, strict=True):
    """
    Return first (most relevant by pymorph) normal form of specified russian word.
    @param unicode word: w
    @param bool strict: if True - process nouns and adverbs only because participle and similar has verbs
            as normal form which is useless for product parsing
    @return:
    """
    global __pymorph_analyzer
    import pymorphy2
    if not __pymorph_analyzer:
        __pymorph_analyzer = pymorphy2.MorphAnalyzer()

    if not strict:
        return __pymorph_analyzer.normal_forms(word)[0]

    # Skip short words or multi-tokens (proposition forms?)
    if len(word) <= 3 or u' ' in word: return word

    # Strict - ignore all except noun and adverbs
    p_variants = __pymorph_analyzer.parse(word)
    """@type: list[pymorphy2.analyzer.Parse]"""
    p_selected = p_variants[0]
    for p in p_variants:
        if p.tag.POS in ('NOUN', 'ADJF', 'ADJS', 'PRTF', 'PRTS'):
            p_selected = p
            break
    parse_norm = p_selected.inflect({'nomn', 'masc', 'sing'})
    if parse_norm:
        w_norm = parse_norm.word
    else:
        w_norm = p_selected.normal_form
    return w_norm if len(w_norm) > 3 else word
