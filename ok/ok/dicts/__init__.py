# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function, absolute_import

from collections import namedtuple
import os
from sys import argv

from ok.settings import ensure_baseline_dir

"""
Basic text processing utils
"""

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
    return None if s is None else s.replace('\u00a0', ' ') if isinstance(s, unicode) else s.replace(b'\xc2\xa0', b' ')


conf_type = namedtuple('OKConfig', 'action toprint baseline_dir default_base_dir prodcsvname cat_csvname '
                       'brands_in_csvname brands_out_csvname '
                       'products_meta_in_csvname products_meta_out_csvname '
                       'product_types_in_json product_types_out_json '
                       'word_forms_dict term_dict')


def main_options(opts=argv, **kwargs):
    """
    @param list[str|unicode] opts: command line tokens starts with script name
    @param dict of (unicode, unicode) kwargs: default param values. File name params will be processed like they passed
                as normal arguments anyway (i.e. relative paths validated etc)
    @return: config
    @rtype: conf_type
    """
    opts = opts[:]
    action = None
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
        elif opt == "-in-products-raw" and len(opts) > 1:
            prodcsvname = opts.pop(1)
        elif not opt.startswith('-') and not action:
            action = opt
        else:
            raise Exception((u"Unknown options: %s" % opt).encode("utf-8"))
    # Defaults
    toprint = toprint or kwargs.get("toprint", "producttypes")
    default_base_dir = ensure_baseline_dir()
    baseline_dir = baseline_dir or kwargs.get("baseline_dir", default_base_dir)

    def build_path_default(param, default_file, _locals=locals()):
        return build_path(baseline_dir, _locals[param], kwargs.get(param, default_file))

    cat_csvname = build_path_default("cat_csvname", 'cats.csv')
    brands_in_csvname = build_path_default("brands_in_csvname", 'brands.csv')
    prodcsvname = build_path_default("prodcsvname", 'products_raw.csv')
    products_meta_in_csvname = build_path_default("products_meta_in_csvname", 'products_meta.csv')
    product_types_in_json = build_path_default("product_types_in_json", 'product_types.json')
    word_forms_dict = build_path_default("word_forms_dict", 'word_forms_dict.txt')
    term_dict = build_path_default("term_dict", 'term_dict.dawg')
    return conf_type(
        action=action,
        toprint=toprint,
        baseline_dir=baseline_dir,
        default_base_dir=default_base_dir,
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


def build_path(baseline_dir, input_path, default_filename):
    import os.path
    if input_path:
        if input_path.startswith('-'):
            raise Exception('File path cannot start with hyphen. It seems confused with option: %s' % input_path)
        if os.path.isabs(input_path):
            return input_path
        input_in_base = os.path.abspath(os.path.join(baseline_dir, input_path))
        if os.path.isfile(input_in_base):
            return input_in_base
        return input_path
    input_path = default_filename and os.path.abspath(os.path.join(baseline_dir, default_filename))
    return input_path


def to_str(something, encoding='utf-8'):
    """@rtype: unicode"""
    # This is to unify conversions from any type to unicode compatible with python 2.7 and 3.3+
    if something is None:
        return None
    if type(something) == unicode:
        return something
    if isinstance(something, unicode):
        return something[:]
    if hasattr(something, '__unicode__'):
        return something.__unicode__()
    s = something.decode(encoding) if isinstance(something, str) else str(something)
    try:
        s = s.decode('unicode-escape')
    except UnicodeEncodeError:
        pass
    try:
        s = s.encode('latin-1').decode('utf-8')
    except UnicodeEncodeError:
        pass
    return s



