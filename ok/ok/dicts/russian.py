# -*- coding: utf-8 -*-
from collections import defaultdict, namedtuple, OrderedDict
import re
from ok.dicts import main_options


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


__pymorph_analyzer = None
"""@type: pymorphy2.MorphAnalyzer"""
__normal_form_word_stats = defaultdict(dict)
"""@type dict of (unicode, dict of (unicode, unicode))"""

WORD_NORMAL_FORM_KEEP_STATS_DEFAULT = True

def _ensure_pymorphy():
    global __pymorph_analyzer

    if not __pymorph_analyzer:
        import pymorphy2
        __pymorph_analyzer = pymorphy2.MorphAnalyzer()

    return __pymorph_analyzer


def get_word_normal_form(word, strict=True, verbose=False, use_external_word_forms_dict=True, collect_stats=WORD_NORMAL_FORM_KEEP_STATS_DEFAULT, return_known=True):
    """
    Return first (most relevant by pymorph) normal form of specified russian word.
    @param unicode word: w
    @param bool strict: if True - process nouns and adverbs only because participle and similar has verbs
            as normal form which is useless for product parsing
    @param bool use_external_word_forms_dict: if False work with pymorphy only.
            It can be useful during data generation when external dicts are not ready or in invalid state
    @param bool return_known: if True (default) return only good known words. No word-creation. If failed to find good
            known form - return word itself. If False, unknown weird words may be returned.
    @return:
    """
    pymorph_analyzer = _ensure_pymorphy()

    if not strict:
        return pymorph_analyzer.normal_forms(word)[0]

    # Skip short words or multi-tokens (proposition forms?)
    # if len(word) <= 3 or u' ' in word: return word
    if len(word) <= 3: return word

    # Strict - ignore all except noun and adverbs
    p_variants = pymorph_analyzer.parse(word)
    """@type: list[pymorphy2.analyzer.Parse]"""
    p_selected = None
    warning_printed = False
    for p in p_variants:
        if p.tag.POS in ('NOUN', 'ADJF', 'ADJS', 'PRTF', 'PRTS') and not ({'Surn'} in p.tag or {'Name'} in p.tag):
            # Ignore names
            if not p_selected:
                p_selected = p
            else:
                if {'NOUN'} not in p_selected.tag and {'NOUN'} in p.tag and p.score >= p_selected.score:
                    # Prefer nouns to other POS with the same score
                    p_selected = p
                    continue

                if {'Geox'} in p_selected.tag and {'Geox'} not in p.tag and p.score >= p_selected.score:
                    # Prefer non-geographical terms if score is the same
                    p_selected = p
                    continue

                if {'NOUN', 'Pltm'} in p.tag and p.score >= p_selected.score:
                    # Special "Pluralia tantum" processing - when meet word which can be in plural form only -
                    # prefer it if its score not less then selected
                    p_selected = p
                    continue

                if verbose and inflect_normal_form(p_selected)[0] != inflect_normal_form(p)[0]:
                    if not warning_printed:
                        print "Morphological ambiguity has been detected for word: %s (selected: %s, %s (%f))" % \
                              (word, p_selected.normal_form, p_selected.tag, p_selected.score),
                    warning_printed = True
                    print "\r\n%s => %s (%f)" % (p.normal_form, p.tag, p.score),
    if warning_printed: print
    # If no one pass the filter just use one with max score
    p_selected = p_selected or p_variants[0]
    w_norm, parse_norm = inflect_normal_form(p_selected)
    # Produced good or bad word form
    is_w_norm_known = is_known_word(w_norm)

    if use_external_word_forms_dict and is_w_norm_known:
        if parse_norm.tag.POS in {'ADJF', 'ADJS'}:
            # Try to convert adjective to noun form
            w_norm = adjective_to_noun_word_form(w_norm, default=w_norm, verbose=verbose)
        if pymorph_analyzer.tag(w_norm)[0].POS in {'NOUN'}:
            # Try to check 'same' and 'pet' forms of noun
            w_norm = noun_from_same_or_pet_word_form(w_norm, default=w_norm, verbose=verbose)

    # Return only long enough words and good known words (if specified, by default)
    result = w_norm if len(w_norm) >= 3 and (not return_known or is_w_norm_known) else word
    if collect_stats:
        __normal_form_word_stats[result][word] = str(p_selected.tag) + (u'?' if not pymorph_analyzer.word_is_known(word) else u'')
    return result


def inflect_normal_form(parse_item):
    """
    Try to inflect one by one sing, masc and nomn. If it cannot be done use previous version.
    If no one inflected just return normal_formal.
    @param pymorphy2.analyzer.Parse parse_item: parse item from MorphAnalyzer
    @rtype: tuple[unicode, pymorphy2.analyzer.Parse]
    """
    result = parse_item
    result = result.inflect({'sing'}) or result
    result = result.inflect({'masc'}) or result
    result = result.inflect({'nomn'}) or result
    return (result.word, result) if result != parse_item else (parse_item.normal_form, parse_item)


def is_known_word(word):
    pymorph_analyzer = _ensure_pymorphy()
    is_known = pymorph_analyzer.word_is_known(word)
    if not is_known:
        word_forms_dict = _ensure_word_forms_dict()
        is_known = word in word_forms_dict
    return is_known

def dump_word_normal_form_stats(filename):
    import os.path
    if __normal_form_word_stats:
        print "Dump stats about %d words to %s" % (len(__normal_form_word_stats), os.path.abspath(filename))
        with open(filename, 'wb') as f:
            f.truncate()
            f.writelines((u'%s: %d; %s\r\n' % (k, len(v), u'; '.join(u'%s=%s' % (w, tag) for w, tag in v.iteritems()))).encode('utf-8')
                         for k, v in sorted(__normal_form_word_stats.iteritems(), key=lambda _v: _v[1], reverse=True))

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
FOLLOWING ARE FUNCTIONS/TASKS TO WORK WITH EXTERNAL DICT DATA
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

class DictArticle(namedtuple('_DictArticle', 'title noun_base same pet')):
    def __dict__(self):
        return self._asdict()

    def is_empty(self):
        return not (self.noun_base or self.same or self.pet)

# Efremova preparations
class _EffrDictParseContext(object):
    def __init__(self, art):
        self.art = art
        """@type: unicode"""
        self.noun_bases = []
        """@type: list[unicode]"""
        self.noun_bases_ambiguity = []
        """@type: list[list[unicode]]"""
        self.same = []
        """@type: list[unicode]"""
        self.same_ambiguity = []
        """@type: list[list[unicode]]"""
        self.pet = []
        """@type: list[unicode]"""
        self.pet_ambiguity = []
        """@type: list[list[unicode]]"""

    def __nonzero__(self):
        return bool(self.art and (self.noun_bases or self.same or self.pet))

    def make_dict_article(self):
        """
        Return main article with all ambiguity clones
        @rtype: list[DictArticle]
        """
        result = [DictArticle(self.art, self.noun_bases, self.same, self.pet)]
        if bool(self.noun_bases_ambiguity) + bool(self.same_ambiguity) + bool(self.pet_ambiguity) > 1:
            raise Exception("Too much ambiguity: only one of noun base, same word and pet name may be ambigue - process manually")
        if self.noun_bases_ambiguity:
            # Ambiguity has been detected. Add all
            for amb in self.noun_bases_ambiguity:
                result.append(DictArticle(self.art, amb, [], []))
        if self.same_ambiguity:
            # Ambiguity has been detected. Add all
            for amb in self.same_ambiguity:
                result.append(DictArticle(self.art, [], amb, []))
        if self.pet_ambiguity:
            # Ambiguity has been detected. Add all
            for amb in self.pet_ambiguity:
                result.append(DictArticle(self.art, [], [], amb))
        return result

def effr_parse(filename, out_filename=None):
    from os.path import getsize, abspath
    effr_dict = defaultdict(list)
    """@type: dict of (unicode, list[DictArticle])"""
    original_dict_file = abspath(filename)
    original_dict_file_size = getsize(original_dict_file)
    print "Parsing Efremova dict from %s (size: %d)" % (original_dict_file, original_dict_file_size)
    with open(filename, 'rb') as f:
        # Articles are separated by empty lines
        art_count = 0
        parse_context = None
        """@type _EffrDictParseContext|None"""
        total_ambiguity_count = 0
        last_line = '\r\n'
        while last_line:
            last_line = f.readline()
            line = last_line.strip().decode('cp1251')
            if line:
                if parse_context is None:
                    # Treat first line of block as article title
                    parse_context = _EffrDictParseContext(line.lower())
                    if art_count % 3000 == 0: print '.',
                    art_count += 1
                    continue
                m = re.search(u'Соотносящийся по знач. с сущ.:(.+?)(?: (?:связанный|унаследованный).*)?$', line, re.U | re.I)
                if m:
                    _parse_article_refs(m.group(1), parse_context, parse_context.noun_bases, parse_context.noun_bases_ambiguity)
                    continue
                m = re.search(u'То же, что:(.+?)\.?$', line, re.U | re.I)
                if m:
                    _parse_article_refs(m.group(1), parse_context, parse_context.same, parse_context.same_ambiguity)
                    continue
                m = re.search(u'(?:Уменьш.|Ласк.) к сущ.:(.+?)\.?$', line, re.U | re.I)
                if m:
                    _parse_article_refs(m.group(1), parse_context, parse_context.pet, parse_context.pet_ambiguity)
                    continue
            if not line:
                # End of article. ready to next
                if parse_context:
                    effr_dict[parse_context.art].extend(parse_context.make_dict_article())
                    total_ambiguity_count += len(parse_context.noun_bases_ambiguity) + \
                                             len(parse_context.same_ambiguity) + \
                                             len(parse_context.pet_ambiguity)
                parse_context = None
        print
        print "Parsed %d terms of %d articles. Found %d ambiguities" % (len(effr_dict), art_count, total_ambiguity_count)

    if out_filename:
        print "Export parsed dict to %s" % abspath(out_filename)
        from datetime import datetime
        now = datetime.now()
        with open(out_filename, 'wb') as f:
            f.truncate()
            f.write('# Generated from "%s" (size: %d) at %s\r\n' % (original_dict_file, getsize(original_dict_file), now))
            for art, items in sorted(effr_dict.iteritems(), key=lambda _i: _i[0]):
                f.write(art.encode('utf-8'))
                for item in items:
                    if item.noun_base:
                        f.write((u'~noun:%s' % (u'|'.join(sorted(item.noun_base)))).encode('utf-8'))
                    if item.same:
                        f.write((u'~same:%s' % (u'|'.join(sorted(item.same)))).encode('utf-8'))
                    if item.pet:
                        f.write((u'~pet:%s' % (u'|'.join(sorted(item.pet)))).encode('utf-8'))
                f.write('\r\n'.encode('utf-8'))

    return effr_dict


def _parse_article_refs(article_refs_list_str, parse_context, context_article_refs, context_article_refs_ambiguity):
    """
    @param unicode article_refs_list_str: list of article references
    @param _EffrDictParseContext parse_context: context
    @param context_article_refs list[unicode]: list of references to other articles (context field)
    @param context_article_refs_ambiguity list[list[unicode]]: list of ambiguity clones (context field)
    @return:
    """
    last_article_refs = _parse_article_references_list_string(article_refs_list_str)
    if not context_article_refs:
        context_article_refs.extend(last_article_refs)
    else:
        prev_article_refs_set = set(context_article_refs)
        last_article_refs_set = set(last_article_refs)
        if prev_article_refs_set != last_article_refs_set:
            # Second meaning of the same article has been found. Omonimia! Ambiguity!
            # First, before panic, try to resolve ambiguity
            if prev_article_refs_set.intersection(last_article_refs_set):
                # Both have common words. Merge
                context_article_refs.extend( [n for n in last_article_refs if n not in context_article_refs] )
            else:
                context_article_refs_ambiguity.append([n for n in last_article_refs if n not in context_article_refs])
                # Select first match as general
                print "WARN: Ambiguity in article %s.\r\n\tFirst: %s\r\n\tSecond: %s" % \
                      (parse_context.art, ', '.join(prev_article_refs_set), ', '.join(last_article_refs))


def _parse_article_references_list_string(ref_list_str):
    article_references = [ref_str.strip().lower() for ref_str in
                       re.findall(u'\s+([^,(]+?)(?:(?:\s+\([^)]+\)),?|,|$)', ref_list_str, re.U)]
    # Get normal forms only
    article_references = OrderedDict.fromkeys(
        [get_word_normal_form(_art_ref, use_external_word_forms_dict=False) for _art_ref in article_references]).keys()
    return article_references

__word_forms_dict = None

def _ensure_word_forms_dict():
    """
    @rtype: dict of (unicode, list[DictArticle])
    """
    from os.path import splitext, isfile
    global __word_forms_dict

    if __word_forms_dict is None:
        word_forms_dict = defaultdict(list)

        config = main_options([])
        filename = config.word_forms_dict

        """
        Load word_form_dicts from multiple files. Sequence (in following order) is checked.
        If file exist override (merge) with previous data.
        <filename>_0.<fileext>
        <filename>_1.<fileext>
        ...
        <filename>_9.<fileext>
        <filename>.<fileext>
        <filename>_override.<fileext>
        Numbered dicts are optional generated dicts from multiple sources.
        One without number suffix is main generated dict
        _override dict contains manual corrections
        """
        file_base, file_ext = splitext(filename)
        file_variants = []
        for i in xrange(10):
            file_variants.append('%s_%d%s' % (file_base, i, file_ext))
        file_variants.append(filename)
        file_variants.append('%s_override%s' % (file_base, file_ext))

        for filename_i in file_variants:
            if isfile(filename_i):
                override_word_forms_dict = _load_word_forms_dict(filename_i)
                for art, items in override_word_forms_dict.iteritems():
                    if art in word_forms_dict:
                        if any(not _it.is_empty() for _it in word_forms_dict[art]) and \
                                all(_it.is_empty() for _it in items):
                            # Do not rewrite existing meaningful data by empty articles
                            continue
                    word_forms_dict[art] = items

        __word_forms_dict = word_forms_dict

    return __word_forms_dict


def _load_word_forms_dict(filename):
    from os.path import abspath
    print "Load word forms dict from: %s" % abspath(filename)
    word_forms_dict = defaultdict(list)

    def take_article_part(forms_variant_str, prefix):
        result = []
        if forms_variant_str.startswith(prefix):
            result = [_s.strip().lower() for _s in forms_variant_str[len(prefix):].split(u'|')]
        return result

    with open(filename, 'rb') as f:
        comment = ''
        all_words = set()
        for line in f:
            line = line.decode('utf-8').strip()
            if not line:
                continue
            if not comment and line.startswith(u'#'):
                comment += line[1:]
                continue
            line = line.split(u'#', 1)[0]  # Remove inline comments

            word, forms_str = (_s.strip().lower() for _s in line.split(u'~', 1))
            all_words.add(word)
            forms_str = forms_str.split(u'~')
            for forms_variant_str in forms_str:
                nouns = take_article_part(forms_variant_str, u'noun:')
                sames = take_article_part(forms_variant_str, u'same:')
                pets = take_article_part(forms_variant_str, u'pet:')
                if nouns or sames or pets:
                    word_forms_dict[word].append(DictArticle(word, nouns, sames, pets))
                    all_words.update(nouns + sames + pets)
        # Put all remaining known referenced words as empty articles to know they are real
        undefined_known_words = all_words.difference(word_forms_dict)
        for word in undefined_known_words:
            word_forms_dict[word].append(DictArticle(word, [], [], []))
    print "Loaded %d word forms (of %d total known words) from file with comment: %s" % \
          (len(word_forms_dict) - len(undefined_known_words), len(word_forms_dict), comment)

    return word_forms_dict

def adjective_to_noun_word_form(word, default=None, verbose=False):
    """
    Lookup at external dictionary and check if specified word is present in 'noun_base' form and then try to convert.
    Ambiguities cases are checked and printed in verbose mode.
    @param unicode word: lookup word
    @param unicode default: return if not found
    @param bool verbose: print about ambiguity
    @rtype: unicode
    """
    word_forms_dict = _ensure_word_forms_dict()

    word = word.lower()
    articles = word_forms_dict.get(word, [])
    word_form = None
    for art in articles:
        if art.noun_base:
            if word_form:
                # Already match one article but another is selected as well
                if verbose:
                    print u"WARN: word %s has ambiguity in external dict. Multiple articles match: %s. Used first one" % \
                          (word, u'; '.join(u'%s: %s' % (_a.title, u', '.join(_a.noun_base)) for _a in articles))
                continue

            min_len = min(map(len, art.noun_base))
            matched_nouns = sorted([n for n in art.noun_base if len(n) == min_len])
            if verbose and len(matched_nouns) > 1:
                print u"WARN: word %s has ambiguity in external dict. Multiple noun bases match: %s. Used first one" % \
                                    (word, ', '.join(art.noun_base))
            word_form = matched_nouns[0]

    if not word_form and u'е' in word and u'ё' not in word:
        # Try to umlaut mutations :)
        pos_e = word.find(u'е')
        while not word_form and pos_e >= 0:
            word_with_ee = word[:pos_e] + u'ё' + word[pos_e + 1:]
            word_form = adjective_to_noun_word_form(word_with_ee)
            pos_e = word.find(u'е', pos_e + 1)

    return word_form or default

def noun_from_same_or_pet_word_form(word, default=None, verbose=False, seen=None):
    """
    Seek NOUN in external dictionary in same and pet names articles. If found try to do this operation
    until find terminal form (same and pet form can be chained in dict)
    @param unicode word: lookup NOUN word
    @param unicode default: return if not found
    @param bool verbose: print about ambiguity
    @rtype: unicode
    """
    # TODO: merge code with adjective_to_noun_word_form()
    word_forms_dict = _ensure_word_forms_dict()

    word = word.lower()
    articles = word_forms_dict.get(word, [])
    word_form = None
    for art in articles:
        if art.same or art.pet:

            if word_form:
                # Already match one article but another is selected as well
                if verbose:
                    print u"WARN: word %s has ambiguity in external dict. Multiple articles match: %s. Used first one" % \
                          (word, u'; '.join(u'%s: %s' % (_a.title, u', '.join(_a.pet + _a.same)) for _a in articles))
                continue

            word_variants = art.same + art.pet
            min_len = min(map(len, word_variants))
            matched_variants = sorted([n for n in word_variants if len(n) == min_len])
            if verbose and len(matched_variants) > 1:
                print u"WARN: word %s has ambiguity in external dict. Multiple pet or same names match: %s. Used first one" % \
                                    (word, ', '.join(word_variants))
            word_form = matched_variants[0]

    if not word_form and u'е' in word and u'ё' not in word:
        # Try to umlaut mutations :)
        pos_e = word.find(u'е')
        while not word_form and pos_e >= 0:
            word_with_ee = word[:pos_e] + u'ё' + word[pos_e + 1:]
            word_form = adjective_to_noun_word_form(word_with_ee)
            pos_e = word.find(u'е', pos_e + 1)

    if word_form and word_form in word_forms_dict:
        # Found word that is itself has variants. Try to do it recursevely
        if not seen or word_form not in seen:
            # Protection from eternal recursion
            seen = seen or set()
            seen.add(word_form)
            word_form = noun_from_same_or_pet_word_form(word_form, default=word_form, verbose=verbose, seen=seen)

    return word_form or default

def ozhogov_parse(filename, out_filename=None):
    # Parse 'same' forms only from Ozhogov dictionary
    from os.path import getsize, abspath
    ozhogov_dict = defaultdict(list)
    """@type: dict of (unicode, list[DictArticle])"""
    original_dict_file = abspath(filename)
    original_dict_file_size = getsize(original_dict_file)
    print "Parsing Ozhogov dict from %s (size: %d)" % (original_dict_file, original_dict_file_size)
    with open(filename, 'rb') as f:
        # All articles one-liners. Start from article title and fields separated by '|'
        # Ambiguities may be on duplicated lines for the same title
        art_count = 0
        total_ambiguity_count = 0
        for line in f:
            line = line.strip().decode('cp1251').lower()
            if line:
                # "сочник|||||== сочень <...mess...>||" - need a title in zero field and '== <ref>' in 5th field.
                # After <ref> token might be a mess, parse first token only
                fields = line.split(u'|')
                if len(fields) < 6:
                    continue
                art = fields[0].strip()

                pymorph = _ensure_pymorphy()
                if pymorph.word_is_known(art):
                    if {'NOUN'} not in pymorph.tag(art)[0]:
                        # Use NOUNs only
                        continue

                art_count += 1
                same = None
                m = re.search(u'==\s+([а-яА-ЯёЁ]+)', fields[5], re.U)
                if m:
                    same = m.group(1)
                if art and same and art != same:
                    previous_arts = ozhogov_dict[art]
                    if any(same in pa.same for pa in previous_arts):
                        # Duplicate
                        continue
                    ozhogov_dict[art].append(DictArticle(art, [], [same], []))
                    total_ambiguity_count += bool(previous_arts)
        print
        print "Parsed %d terms of %d articles. Found %d ambiguities" % (len(ozhogov_dict), art_count, total_ambiguity_count)

    if out_filename:
        print "Export parsed dict to %s" % abspath(out_filename)
        from datetime import datetime
        now = datetime.now()
        with open(out_filename, 'wb') as f:
            f.truncate()
            f.write('# Generated from "%s" (size: %d) at %s\r\n' % (original_dict_file, getsize(original_dict_file), now))
            for art, items in sorted(ozhogov_dict.iteritems(), key=lambda _i: _i[0]):
                f.write(art.encode('utf-8'))
                for item in items:
                    if item.same:
                        f.write((u'~same:%s' % (u'|'.join(sorted(item.same)))).encode('utf-8'))
                f.write('\r\n'.encode('utf-8'))

    return ozhogov_dict

if __name__ == '__main__':
    import sys

    if sys.argv and sys.argv[1] == 'efremova':
        # Generate word forms from Efremova dictionary
        effr_dict_filename = sys.argv[2]
        word_forms_out_filename = sys.argv[3]
        effr_parse(effr_dict_filename, word_forms_out_filename)

    if sys.argv and sys.argv[1] == 'ozhogov':
        # Generate word forms from Ozhogov dictionary
        ozhogov_dict_filename = sys.argv[2]
        word_forms_out_filename = sys.argv[3]
        ozhogov_parse(ozhogov_dict_filename, word_forms_out_filename)
