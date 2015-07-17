# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
from collections import namedtuple

import logging
import itertools
import re

from whoosh.fields import TEXT, ID, SchemaClass
from whoosh import query as whoosh_query, collectors, analysis, sorting
from whoosh.idsets import BitSet
from ok.query.whoosh_contrib.utils import ResultsPreCachedStoredFields

from ok.utils import to_str
from ok.dicts.term import TYPE_TERM_PROPOSITION_LIST, TypeTerm
from ok.query import parse_query
from ok.query.tokens import QueryToken

from ok.query.whoosh_contrib.base import BaseFindQuery
from ok.query.whoosh_contrib import utils

log = logging.getLogger(__name__)

""""""""""""""""""""""""""" INDEX PART """""""""""""""""""""""""""""

INDEX_NAME = 'Brands.idx'


class BrandTokenizer(analysis.Tokenizer):

        def __call__(self, value, removestops=False, **kwargs):
            t = analysis.acore.Token(removestops=removestops, **kwargs)

            tokens = parse_query(value).tokens
            for i, token in enumerate(tokens):
                if i > 0 and token in TYPE_TERM_PROPOSITION_LIST:
                    # Filter out all propositions except starting one
                    continue
                t.text = to_str(token)
                t.boost = 1.0
                yield t


class BrandsSchema(SchemaClass):
    brand = TEXT(stored=True,
                 vector=True,
                 analyzer=BrandTokenizer(),
                 phrase=False)

    serial_28 = ID()

SCHEMA = BrandsSchema()
"""@type: whoosh.fields.Schema"""

_brands_inited = False


def get_brand_data(brand_name, manufacturer=False):
    global _brands_inited
    from ok.dicts import main_options
    from ok.dicts.brand import Brand

    if not _brands_inited:
        if not Brand.all():
            config = main_options([])
            Brand.from_csv(config.brands_in_csvname)
        _brands_inited = True

    return Brand.exist(brand_name) if not manufacturer else Brand.findOrCreate_manufacturer_brand(brand_name, add_pattern_synonyms=False)


def products_data_source():
    from ok.dicts import main_options
    from ok.dicts.product import Product

    config = main_options([])
    return Product.from_meta_csv(config.products_meta_in_csvname)


def feeder(writer):
    seen = set()
    not_a_term = TypeTerm.not_a_term_character_pattern
    for product in products_data_source():
        brand_variants = []
        brand_name = product['brand']
        if brand_name:
            brand = get_brand_data(brand_name)
            if brand and not brand.no_brand and brand not in seen:
                brand_variants.append(brand)

        manufacturer_name = product['product_manufacturer']
        if manufacturer_name:
            manufacturer_brand = get_brand_data(manufacturer_name, manufacturer=True)
            if manufacturer_brand and manufacturer_brand not in brand_variants and not manufacturer_brand.no_brand and manufacturer_brand not in seen:
                brand_variants.append(manufacturer_brand)

        if brand_variants:
            for brand in brand_variants:
                seen_term = set()
                for brand_term in [brand.name] + brand.synonyms:
                    if brand_term in seen_term:
                        continue
                    normalized_term = re.sub(not_a_term, ' ', brand_term)
                    normalized_brand = re.sub(not_a_term, ' ', brand.name)
                    # Naive brand vs synonym similarity check
                    boost = 1.5 if normalized_term == normalized_brand else 1.0

                    writer.add_document(brand=brand_term, _stored_brand=brand.name, _brand_boost=boost)
                    seen_term.add(brand_term)

                    if normalized_term not in seen_term:
                        writer.add_document(brand=normalized_term, _stored_brand=brand.name, _brand_boost=boost)

                seen.add(brand)

    return data_checksum()


def data_checksum():
    """@rtype: long"""
    from ok.dicts import main_options
    config = main_options([])
    return utils.text_data_file_checksum(config.brands_in_csvname)

""""""""""""""""""""""""""" SEARCH PART """""""""""""""""""""""""""""

MIN_BRAND_PREFIX_LEN = 3
MatchedPos = namedtuple('MatchedPos', 'start_pos end_pos brand_terms_set docnum')


class FindBrandsQuery(BaseFindQuery):
    index_name = INDEX_NAME
    need_matched_terms = False
    schema = SCHEMA

    def query_variants(self):
        tokens = self.q_tokenized
        min_len = MIN_BRAND_PREFIX_LEN

        token_queries = []
        seen = set()
        for token in sorted(tokens, key=len, reverse=True):
            if token not in seen:
                seen.add(token)
                prefixes = self.expand_term_prefix('brand', token)
                first_term = next(prefixes, None)
                if first_term is not None:
                    # If index does not know wither token or its prefixed forms then nothing to search
                    token_len = len(token)

                    if token_len < min_len:
                        if first_term != token:
                            # First term in prefixes is always self term if it is in the index.
                            continue
                        token_queries.append(whoosh_query.Term('brand', token, boost=2.0))
                    else:
                        prefix_queries = []
                        for i, prefix in enumerate(itertools.chain([first_term], prefixes)):
                            if (i == 0 and token == prefix) or prefix not in seen:
                                seen.add(prefix)
                                boost = 2.0 if prefix == token else 1.0 + (token_len - min_len)*0.1
                                prefix_queries.append(whoosh_query.Term('brand', prefix, boost=boost))

                        token_queries += utils.and_or_query(prefix_queries, And=None, Or=whoosh_query.DisjunctionMax)

        return utils.and_or_query(token_queries, Or=whoosh_query.DisjunctionMax)

    class BrandsCollector(collectors.ScoredCollector):

        def __init__(self, original_query_tokens, group_limit, sort_brands=False, seen_docset=None, stored_fields=None):
            super(FindBrandsQuery.BrandsCollector, self).__init__()
            self.original_query_tokens = original_query_tokens

            self.group_limit = group_limit
            self.sort_brands = sort_brands

            self.items = None
            self.seen_docset = seen_docset

            self._terms_cache = dict()
            self.brands_found = dict()
            """@type: dict of (unicode, list[list[MatchedPos]])"""
            self._stored_fields = stored_fields if stored_fields is not None else dict()
            """@type: dict of (int, dict of (unicode, unicode))"""

        def _terms(self, reader, global_docnum):
            terms_cache = self._terms_cache
            if global_docnum not in terms_cache:
                brand_terms = set(reader.vector(global_docnum, 'brand').all_ids())

                from dawg import BytesDAWG
                brand_terms_dawg = BytesDAWG(zip(brand_terms, map(chr, range(len(brand_terms)))))

                terms_cache[global_docnum] = (brand_terms, brand_terms_dawg)
            else:
                brand_terms, brand_terms_dawg = terms_cache[global_docnum]
            return brand_terms, brand_terms_dawg

        def stored_fields(self, reader, global_docnum):
            stored_fields = self._stored_fields
            fields = stored_fields.get(global_docnum)
            if fields is None:
                fields = reader.stored_fields(global_docnum) or {}
                stored_fields[global_docnum] = fields
            return fields

        def count(self):
            return len(self.items)

        def token_matches(self, reader, token, global_docnum, terms_prefix_dict=None):
            """
            Check if one original query token matches brand terms in specified document.
            Original token can be prefix or another term transformation
            If matches found returns BitSet object with indexes of potential matches in prefix_dict
            Later this bitset can be used for intersection with other matches
            @param reader: IndexReader
            @param ok.query.tokens.QueryToken token: original query token
            @param int global_docnum: document in Brands index
            @rtype: BitSet|None
            """
            if terms_prefix_dict is None:
                _, terms_prefix_dict = self._terms(reader, global_docnum)
            token_len = len(token)

            if token_len >= MIN_BRAND_PREFIX_LEN:
                term_indexes = map(lambda _i: ord(_i[1]), terms_prefix_dict.items(token[:]))
            else:
                term_idx = terms_prefix_dict.get(token)
                term_indexes = [ord(term_idx[0])] if term_idx else []

            if term_indexes:
                # Prefixed terms found. Save their indexes in bitset
                return BitSet(term_indexes)

        def collect_matches(self):
            reader = self.top_searcher.reader()
            original_query_tokens = self.original_query_tokens
            # Collect distinct brand names if brands_limit was specified to calculate when stop collection
            brands_found = self.brands_found

            # Cache methods for call optimization
            stored_fields = self.stored_fields
            _collect = self._collect
            token_matches = self.token_matches
            terms_for_doc = self._terms

            seen_docset = self.seen_docset

            for sub_docnum in self.matches():

                global_docnum = self.offset + sub_docnum
                if seen_docset is not None:
                    if global_docnum in seen_docset:
                        continue
                    seen_docset.add(global_docnum)

                brand_terms, terms_prefix_dict = terms_for_doc(reader, global_docnum)
                brand_length = len(brand_terms)

                # For Multi token brand: Brand tokens can occur in query in any order but always must be in one phrase
                end = len(original_query_tokens)
                found_tokens_bitset = []
                matched_pos = []
                for i, token in enumerate(original_query_tokens):
                    if i + brand_length > end:
                        # Not enough tokens for next match
                        break
                    match_bitset = token_matches(reader, token, global_docnum, terms_prefix_dict=terms_prefix_dict)
                    if match_bitset:
                        found_tokens_bitset.append(match_bitset)
                        # NOTE: First brand token may be a proposition. Do not check here
                        start_pos = end_pos = token.position
                        j = i + 1
                        while j < end and len(found_tokens_bitset) < brand_length:
                            # Check next tokens are set of matched brand terms
                            next_token = original_query_tokens[j]
                            if next_token in TYPE_TERM_PROPOSITION_LIST:
                                pass
                            else:
                                match_bitset = token_matches(reader, next_token, global_docnum, terms_prefix_dict=terms_prefix_dict)
                                if not match_bitset:
                                    # Break the sequence and restart from next token
                                    found_tokens_bitset = []
                                    break
                                else:
                                    found_tokens_bitset.append(match_bitset)
                                    end_pos = next_token.position
                            j += 1

                        else:
                            if any(len(set(term_comb)) == brand_length for term_comb in itertools.product(*found_tokens_bitset)):
                                # Check that one of prefix combinations makes full length brand sequence
                                # One match found. Keep match and prepare for next cycle
                                matched_pos.append(MatchedPos(start_pos, end_pos, set(brand_terms), global_docnum))

                            found_tokens_bitset = []

                if matched_pos:
                    # All brand tokens found in the query as a sub-sequence
                    score = self.matcher.score()
                    fields = stored_fields(reader, global_docnum)
                    brand = fields['brand']
                    _collect(global_docnum, score)

                    if brand not in brands_found:
                        brands_found[brand] = [score, matched_pos]

                    else:
                        old_score, brand_matched_pos = brands_found[brand]
                        brands_found[brand][0] = max(score, old_score)
                        brand_matched_pos.extend(matched_pos)

                elif log.isEnabledFor(logging.DEBUG):
                    log.debug("Filtered out: %s. Query: %s", ' + '.join(brand_terms), self.q)

        def _collect(self, global_docnum, score):
            self.items.append((score, global_docnum))
            self.docset.add(global_docnum)
            return 0 - score

        def doc_brand(self, global_docnum):
            reader = self.top_searcher.reader()
            fields = self.stored_fields(reader, global_docnum)
            brand = fields['brand']
            return brand

        def sort_key(self, sub_docnum):
            global_docnum = self.offset + sub_docnum
            score = self.matcher.score()

            # Sort by score
            key = 0 - score

            if self.sort_brands:
                brand = self.doc_brand(global_docnum)
                key = (brand, key)

            return key

        def results(self):
            docset = self.docset
            items = self.items
            """@type: list"""

            if items:
                # Sort by first element in tuple, i.e. key. If two items have identical key,
                # than docnum is used (i.e. second element). 3rd and 4th elements wont used in sorting because docnum is unique
                doc_brand = self.doc_brand
                key = (lambda _i: 0-_i[0]) if not self.sort_brands else (lambda _i: (doc_brand(_i[1]), 0-_i[0]))
                items.sort(key=key)

                if self.group_limit is not None:
                    # Clean up possible low-score brand matches
                    # Items are sorted already. Thus, just look forward until n-th different key
                    group_count_down = self.group_limit + 1
                    prev_key = last = None
                    key = (lambda _i: 0-_i[0]) if not self.sort_brands else (lambda _i: doc_brand(_i[1]))
                    for i, item in enumerate(items):
                        this_key = key(item)
                        if prev_key is None or this_key != prev_key:
                            prev_key = this_key
                            group_count_down -= 1
                            if not group_count_down:
                                last = i
                                break

                    if last is not None:
                        items = self.items = items[:last]

            results = self._results(items, docset=docset)
            return results

        def _results(self, items, **kwargs):
            r = ResultsPreCachedStoredFields(self._stored_fields, self.top_searcher, self.q, items, **kwargs)
            r.runtime = self.runtime
            r.collector = self
            return r

    def _search(self, searcher, wq, **kwargs):
        """
        @param whoosh.searching.Searcher searcher: index searcher
        @param whoosh.query.qcore.Query whoosh_query: one of query produced by @query_variants()
        """
        collector = self._collector(**kwargs)
        searcher.search_with_collector(wq, collector)

        return collector.results()

    _seen_docset = None
    _stored_fields = None

    def _collector(self, limit=1, sortedby=None, groupedby=None, **_):
        assert groupedby is None, 'Brands search does not support facets at the moment'
        if isinstance(sortedby, sorting.ScoreFacet):
            sort_brands = False  # Default behaviour
        elif isinstance(sortedby, sorting.FieldFacet) and sortedby.fieldname == 'brand':
            sort_brands = True
        else:
            raise AssertionError('%s supports only Score and "brand" field sorting' % self.__class__.__name__)

        seen_docset = self._seen_docset = self._seen_docset or set()
        stored_fields = self._stored_fields = self._stored_fields or dict()

        collector = self.BrandsCollector(self.q_tokenized.tokens, group_limit=limit, sort_brands=sort_brands,
                                         seen_docset=seen_docset, stored_fields=stored_fields)
        return collector

    def matched_brand_positions(self):
        """
        Returns list of matched token positions of original query where brand of current match was found
        """
        collector = self._results.collector
        """@type: ok.query.whoosh_contrib.find_brands.FindBrandsQuery.BrandsCollector"""
        brand = self.current_match['brand']
        pos = collector.brands_found[brand][1]
        return pos

    @property
    def matched_tokens(self):
        pos = self.matched_brand_positions()

        q_tokenized = self.q_tokenized
        tokens = []
        if pos:
            for pos_item in pos:
                tokens.extend(filter(lambda token: isinstance(token, QueryToken), q_tokenized[pos_item.start_pos: pos_item.end_pos + 1]))
        return tokens

    @property
    def matched_terms(self):
        docnum = self.current_match.docnum
        pos = self.matched_brand_positions()

        matched_terms = set()
        if pos:
            for pos_item in pos:
                if pos_item.docnum == docnum:
                    matched_terms.update(pos_item.brand_terms_set)
        return matched_terms
