# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

import logging
import itertools
import re

from whoosh.fields import TEXT, ID, SchemaClass
from whoosh import query as whoosh_query, collectors, analysis

from ok.utils import to_str
from ok.dicts.term import TYPE_TERM_PROPOSITION_LIST, TypeTerm
from ok.query import parse_query
from ok.query.tokens import QueryToken

from ok.query.whoosh_contrib.base import BaseFindQuery
from ok.query.whoosh_contrib import utils

log = logging.getLogger(__name__)

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
    for product in Product.from_meta_csv(config.products_meta_in_csvname):
        yield product


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

MIN_BRAND_PREFIX_LEN = 3


class FindBrandsQuery(BaseFindQuery):
    index_name = INDEX_NAME
    need_matched_terms = False

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

                        if prefix_queries:
                            if len(prefix_queries) == 1:
                                token_queries.append(prefix_queries[0])
                            else:
                                token_queries.append(whoosh_query.Or(prefix_queries))

        queries = []
        if token_queries:
            if len(token_queries) == 1:
                queries.append(token_queries[0])
            else:
                queries.append(whoosh_query.And(token_queries))
                queries.append(whoosh_query.Or(token_queries))
        return queries

    class BrandsCollector(collectors.WrappingCollector):

        def __init__(self, child, original_query_tokens, brands_limit, seen_docset=None):
            super(FindBrandsQuery.BrandsCollector, self).__init__(child)
            self.original_query_tokens = original_query_tokens
            self.brands_limit = brands_limit
            self.matched_brand_pos = dict()
            self.seen_docset = seen_docset
            self._brand_cache = dict()
            self.brands_found = dict()

        def _stored_brand(self, reader, global_docnum):
            brand_cache = self._brand_cache
            if global_docnum not in brand_cache:
                brand = reader.stored_fields(global_docnum)['brand']
                brand_terms = set(reader.vector(global_docnum, 'brand').all_ids())

                from dawg import CompletionDAWG
                brand_terms_dawg = CompletionDAWG(brand_terms)

                brand_cache[global_docnum] = (brand, brand_terms, brand_terms_dawg)
            else:
                brand, brand_terms, brand_terms_dawg = brand_cache[global_docnum]
            return brand, brand_terms, brand_terms_dawg

        def count(self):
            return len(self.brands_found)

        def token_matches(self, reader, token, global_docnum):
            """
            Check if one original query token matches brand terms in specified document.
            Original token can be prefix or another term transformation
            @param reader: IndexReader
            @param ok.query.tokens.QueryToken token: original query token
            @param int global_docnum: document in Brands index
            @rtype: bool
            """
            brand_terms_dawg = self._stored_brand(reader, global_docnum)[2]
            token_len = len(token)

            return (token_len >= MIN_BRAND_PREFIX_LEN and brand_terms_dawg.has_keys_with_prefix(token[:])) or \
                   (token_len < MIN_BRAND_PREFIX_LEN and token in brand_terms_dawg)

        def collect_matches(self):
            reader = self.top_searcher.reader()
            original_query_tokens = self.original_query_tokens
            limit_count = self.brands_limit
            # Collect distinct brand names if brands_limit was specified to calculate when stop collection
            brands_found = self.brands_found
            seen_docset = self.seen_docset
            token_matches = self.token_matches
            stored_brand = self._stored_brand

            for sub_docnum in self.matches():

                global_docnum = self.offset + sub_docnum
                if seen_docset is not None:
                    if global_docnum in seen_docset:
                        continue
                    seen_docset.add(global_docnum)

                brand, brand_terms, _ = stored_brand(reader, global_docnum)
                brand_length = len(brand_terms)

                score = self.child.matcher.score()
                min_score_brand = None
                if brands_found:
                    if limit_count is not None and brand not in brands_found:
                        min_score_brand, min_score_value = min(brands_found.items(), key=lambda _t: _t[1][0])
                        if limit_count == 0 and score <= min_score_value[0]:
                            # Score of current doc's brand is too low to be selected in brands_found.
                            continue

                # For Multi token brand: Brand tokens can occur in query in any order but always must be in one phrase
                end = len(original_query_tokens)
                found_brand_tokens = set()
                matched_pos = []
                for i, token in enumerate(original_query_tokens):
                    if token_matches(reader, token, global_docnum):
                        found_brand_tokens.add(token)
                        # NOTE: First brand token may be a proposition. Do not check here
                        start_pos = end_pos = token.position
                        j = i + 1
                        while j < end and len(found_brand_tokens) < brand_length:
                            # Check next tokens are set of matched brand terms
                            next_token = original_query_tokens[j]
                            if next_token in TYPE_TERM_PROPOSITION_LIST:
                                pass
                            elif not token_matches(reader, next_token, global_docnum):
                                # Break the sequence and restart from next token
                                found_brand_tokens.clear()
                                break
                            else:
                                found_brand_tokens.add(next_token)
                                end_pos = next_token.position
                            j += 1
                        else:
                            if len(found_brand_tokens) == brand_length:
                                # One match found. Keep match and prepare for next cycle
                                matched_pos.append((start_pos, end_pos, set(brand_terms), global_docnum))
                            found_brand_tokens.clear()
                            if i + brand_length >= end:
                                # Not enough tokens for next match
                                break

                if matched_pos:
                    # All brand tokens found in the query as a sub-sequence
                    self.collect(sub_docnum)

                    if brand not in brands_found:
                        if limit_count is not None:
                            if limit_count > 0:
                                limit_count -= 1
                            elif min_score_brand:
                                # Replace min_score_brand. Score of current doc was checked already on the cycle start
                                del brands_found[min_score_brand]

                        # TODO: keep matched pos list separately from brands_found because
                        # brand may be deleted from brands_found due to limit but later another document appears for that brand with higher score
                        # Than, previous low score matches will be lost
                        brands_found[brand] = [score, matched_pos]
                        self.matched_brand_pos[global_docnum] = matched_pos
                    else:
                        old_score, brand_matched_pos = brands_found[brand]
                        brands_found[brand][0] = max(score, old_score)
                        brand_matched_pos.extend(matched_pos)
                        self.matched_brand_pos[global_docnum] = brand_matched_pos

                elif log.isEnabledFor(logging.DEBUG):
                    log.debug("Filtered out: %s. Query: %s", ' + '.join(brand_terms), self.child.q)

        def results(self):
            if self.brands_limit is not None:
                # Clean up possible low-score brand matches
                docset = self.child.docset
                items = self.child.items
                """@type: list"""

                filtered_brands = self.brands_found
                stored_brand = self._stored_brand
                reader = self.top_searcher.reader()

                shift = 0
                for i in range(len(items)):
                    docnum = items[i + shift][1]
                    brand = stored_brand(reader, docnum)[0]
                    if brand not in filtered_brands:
                        docset.remove(docnum)
                        del items[i + shift]
                        shift -= 1

            return self.child.results()

    def _search(self, searcher, wq, **kwargs):
        """
        @param whoosh.searching.Searcher searcher: index searcher
        @param whoosh.query.qcore.Query whoosh_query: one of query produced by @query_variants()
        """
        collector = self._collector(kwargs)
        searcher.search_with_collector(wq, collector)

        results = collector.results()
        results.matched_brand_pos = collector.matched_brand_pos

        return results

    _seen_docset = None

    def _collector(self, kwargs):
        assert kwargs.get('groupedby') is None, 'Brands search does not support facets at the moment'
        limit = kwargs.pop('limit', 1)

        seen_docset = self._seen_docset = self._seen_docset or set()

        wrapped_collector = collectors.UnlimitedCollector()
        collector = self.BrandsCollector(wrapped_collector, self.q_tokenized.tokens, brands_limit=limit, seen_docset=seen_docset)
        return collector

    @property
    def matched_tokens(self):
        pos = self._results.matched_brand_pos.get(self.current_match.docnum)
        q_tokenized = self.q_tokenized
        tokens = []
        if pos:
            for pos_item in pos:
                tokens.extend(filter(lambda token: isinstance(token, QueryToken), q_tokenized[pos_item[0]: pos_item[1] + 1]))
        return tokens

    @property
    def matched_terms(self):
        docnum = self.current_match.docnum
        pos = self._results.matched_brand_pos.get(docnum)
        matched_terms = set()
        if pos:
            for pos_item in pos:
                if pos_item[3] == docnum:
                    matched_terms.update(pos_item[2])
        return matched_terms
