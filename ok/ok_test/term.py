# -*- coding: utf-8 -*-
import ok.dicts
import ok.dicts.term
import ok.dicts.product_type
import ok.dicts.product_type_dict

def test_context_terms(config=None):
    test_source = 'Full' if not config else config.product_types_in_json
    print "test_context_terms(%s)" % test_source
    ok.dicts.term.TypeTerm.term_dict.clear()
    pd = ok.dicts.product_type_dict.reload_product_type_dict(config)
    rel = pd.find_product_type_relations(u'продукт йогуртный перс/мар/ананас/дыня')

    pt_mar_bad_parent = ok.dicts.product_type.ProductType(u'продукт', u'мар')
    pt_mar = ok.dicts.product_type.ProductType(u'продукт', u'йогуртный', u'мар')
    pt_mar_full = ok.dicts.product_type.ProductType(u'продукт', u'йогуртный', u'маракуйя')
    eq_releation = pt_mar.equals_to(pt_mar_full, dont_change=True)

    assert pt_mar in rel
    assert pt_mar_bad_parent not in rel
    assert eq_releation in rel[pt_mar]

    # Only in test data
    if test_source != 'Full':
        subset_of_relation = pt_mar.subset_of(pt_mar_bad_parent, dont_change=True)
        assert subset_of_relation in rel[pt_mar]

    print "test_context_terms(): success"


def test_context_terms_parse(config=None):
    print "test_context_terms_parse(%s)" % ('Full' if not config else config.product_types_in_json)
    ok.dicts.term.TypeTerm.term_dict.clear()
    pd = ok.dicts.product_type_dict.reload_product_type_dict(config)
    types = pd.collect_sqn_type_tuples(u'продукт йогуртный перс/мар/ананас/дыня')
    for t in types:
        try:
            list(t.get_main_form_term_ids())
        except ok.dicts.term.ContextRequiredTypeTermException as e:
            print "Test failed: All types after parse must be in terminal context"
            raise
    pt_mar = ok.dicts.product_type.ProductType(u'продукт', u'йогуртный', u'мар')
    pt_mar_not_context = ok.dicts.product_type.ProductType(u'продукт', u'маракуйя')
    pt_mar_full = ok.dicts.product_type.ProductType(u'продукт', u'йогуртный', u'маракуйя')

    assert pt_mar in types and pt_mar_full in types and pt_mar_not_context in types
    print "test_context_terms_parse(): success"


def get_test_config():
    config = ok.dicts.main_options(
        ['test.py', '-base-dir', 'resources\\test', '-in-product-types-json', 'product_types_test_mar.json'])
    return config


def test_dawg_persistence():
    print "test_dawg_persistence()"
    filename = 'out/_term_dict_test.dawg'
    test_term_dict_saved = ok.dicts.term.dump_term_dict_from_product_types(filename)
    test_term_dict_loaded = ok.dicts.term.load_term_dict(filename)
    max_id = test_term_dict_loaded.get_max_id()
    assert test_term_dict_saved.get_max_id() == max_id and max_id > 0, "Saved and loaded dawgs are different size!"
    for i in xrange(1, max_id + 1):
        term_saved = test_term_dict_saved.get_by_id(i)
        term_loaded = test_term_dict_loaded.get_by_id(i)
        assert isinstance(term_saved, ok.dicts.term.TypeTerm) and isinstance(term_loaded, ok.dicts.term.TypeTerm), \
            "Terms have bad type"
        assert term_saved == term_loaded and type(term_saved) == type(term_loaded), \
            "Saved and Loaded terms are different!"
    print "test_dawg_persistence(): success"


if __name__ == '__main__':
    import ok_test.term
    try:
        test_context_terms_parse(get_test_config())
        print u'-' * 40
        ok_test.term.test_context_terms(get_test_config())

        # Full
        print u'-' * 40
        ok_test.term.test_context_terms()

        # dawg persistence
        print u'-' * 40
        ok_test.term.test_dawg_persistence()
    except Exception as e:
        print unicode(e)
        raise
