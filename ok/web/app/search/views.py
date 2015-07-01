# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
from collections import OrderedDict, defaultdict

from flask import render_template, Blueprint, jsonify, request

from ok.dicts import to_str
from ok.dicts.term import TypeTerm
from ok.query import find_products

from app import cache, data_config

mod = Blueprint('search', __name__, url_prefix='/search')


@cache.cached(key_prefix='_get_term_dict')
def get_term_dict():
    """@rtype: TypeTermDict"""
    term_dict = TypeTerm.term_dict.from_file(data_config.term_dict, verbose=True, skip_word_forms_validation=True)
    term_dict.print_stats()
    return term_dict


@mod.before_app_first_request
def init_data():
    get_term_dict()


@mod.route("/", methods=['GET', 'POST'])
def enter():
    try:
        q = request.form['q']
    except KeyError:
        q = request.args.get('q', '')

    if not q:
        entries = []
        facets = {}
    else:
        facet_fields = ['types']
        with find_products(q, limit=None, return_fields=['pfqn', 'types'], facet_fields=facet_fields) as rs:
            entries = [{'header': 'query', 'value': to_str(repr(rs.query))},
                       {'header': 'size', 'value': rs.size}]
            for pfqn, types in rs.data:
                entry = {'pfqn': pfqn, 'score': rs.score, 'types': to_str(types), 'matched': to_str(rs._fetcher.current_match.matched_terms())}
                entries.append(entry)
            facets = defaultdict(OrderedDict)
            for facet in facet_fields:
                counts = rs.facet_counts(facet)
                facets[facet].update(counts)

    return render_template('search/landing.html', q=q, entries=entries, product_list=[], facets=facets)


@mod.route("/suggest/json")
def suggest_json():
    q = request.args.get('term')
    with find_products(q, return_fields=['pfqn']) as rs:
        results = [('', to_str(repr(rs.query))), ('', 'Found %d results' % rs.size)]
        results.extend((pfqn, pfqn) for pfqn in rs.data)
    return jsonify({'results': [{'label': it[1], 'value': it[0]} for it in results]})


@mod.route("/product/summary/json")
def product_summary_json():
    q = request.args.get('q')
    results = [{'pfqn': q}]
    return jsonify({'results': results})
