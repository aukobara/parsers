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
    import pymorphy2

    if not __pymorph_analyzer:
        __pymorph_analyzer = pymorphy2.MorphAnalyzer()

    return __pymorph_analyzer


def get_word_normal_form(word, strict=True, verbose=False, use_external_word_forms_dict=True, collect_stats=WORD_NORMAL_FORM_KEEP_STATS_DEFAULT):
    """
    Return first (most relevant by pymorph) normal form of specified russian word.
    @param unicode word: w
    @param bool strict: if True - process nouns and adverbs only because participle and similar has verbs
            as normal form which is useless for product parsing
    @param bool use_external_word_forms_dict: if False work with pymorphy only.
            It can be useful during data generation when external dicts are not ready or in invalid state
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

    if use_external_word_forms_dict and parse_norm.tag.POS in {'ADJF', 'ADJS'}:
        # Try to convert adjective to noun form
        w_norm = get_word_form_external(w_norm, default=w_norm, verbose=verbose)

    result = w_norm if len(w_norm) >= 3 else word
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

class DictArticle(namedtuple('_DictArticle', 'title noun_base')):
    def __dict__(self):
        return self._asdict()

# Efremova preparations
def effr_parse(filename, out_filename=None):
    from os.path import getsize, abspath
    effr_dict = defaultdict(list)
    """@type: dict of (unicode, list[DictArticle])"""
    original_dict_file = abspath(filename)
    original_dict_file_size = getsize(original_dict_file)
    print "Parsing Efremova dict from %s (size: %d)" % (original_dict_file, original_dict_file_size)
    with open(filename, 'rb') as f:
        # Articles are separated by empty lines
        art = ''
        noun_bases = []
        noun_bases_ambiguity = []
        art_count = 0
        ambiguity_count = 0
        for line in f:
            line = line.strip().decode('cp1251')
            if line:
                if not art:
                    art = line.lower()
                    if art_count % 3000 == 0: print '.',
                    art_count += 1
                    continue
                m = re.search(u'Соотносящийся по знач. с сущ.:(.+?)(?: связанный с ним.*?)?$', line, re.U | re.I)
                if m:
                    prev_noun_bases = noun_bases
                    prev_noun_bases_set = set(prev_noun_bases)
                    noun_list_str = m.group(1)
                    last_noun_bases = [noun_str.strip().lower() for noun_str in re.findall(u'\s+([^,(]+?)(?:(?:\s+\([^)]+\)),?|,)', noun_list_str, re.U)]
                    last_noun_bases = OrderedDict.fromkeys([get_word_normal_form(_n, use_external_word_forms_dict=False) for _n in last_noun_bases]).keys()
                    last_noun_bases_set = set(last_noun_bases)
                    if prev_noun_bases_set and prev_noun_bases_set != last_noun_bases_set:
                        # Second meaning of the same article has been found. Omonimia! Ambiguity!
                        # First, before panic, try to resolve ambiguity
                        if prev_noun_bases_set.intersection(last_noun_bases_set):
                            # Both have common words. Merge
                            noun_bases = prev_noun_bases + [n for n in last_noun_bases if n not in prev_noun_bases]
                        else:
                            noun_bases_ambiguity.append([n for n in last_noun_bases if n not in prev_noun_bases])
                            noun_bases = prev_noun_bases
                            ambiguity_count += 1
                            print "WARN: Ambiguity in article %s.\r\n\tFirst: %s\r\n\tSecond: %s" % \
                                  (art, ', '.join(prev_noun_bases_set), ', '.join(last_noun_bases))
                    else:
                        noun_bases = last_noun_bases
            else:
                # End of article. ready to next
                if art and noun_bases:
                    effr_dict[art].append(DictArticle(art, noun_bases))
                    for amb_bases in noun_bases_ambiguity:
                        effr_dict[art].append(DictArticle(art, amb_bases))
                art = u''
                noun_bases = []
                noun_bases_ambiguity = []
        print
        print "Parsed %d terms of %d articles. Found %d ambiguities" % (len(effr_dict), art_count, ambiguity_count)

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
                    f.write((u'~noun:%s' % (u'|'.join(sorted(item.noun_base)))).encode('utf-8'))
                f.write('\r\n'.encode('utf-8'))

    return effr_dict

__word_forms_dict = None

def _ensure_word_forms_dict():
    """
    @rtype: dict of (unicode, list[DictArticle])
    """
    from os.path import splitext, isfile
    global __word_forms_dict

    if __word_forms_dict is None:
        config = main_options([])
        filename = config.word_forms_dict
        word_forms_dict = _load_word_forms_dict(filename)

        file_base, file_ext = splitext(filename)
        override_filename = file_base + '_override' + file_ext
        if isfile(override_filename):
            override_word_forms_dict = _load_word_forms_dict(override_filename)
            word_forms_dict.update(override_word_forms_dict)

        __word_forms_dict = word_forms_dict

    return __word_forms_dict

def _load_word_forms_dict(filename):
    from os.path import abspath
    print "Load word forms dict from: %s" % abspath(filename)
    word_forms_dict = defaultdict(list)
    with open(filename, 'rb') as f:
        comment = ''
        for line in f:
            line = line.decode('utf-8').strip()
            if not line:
                continue
            if not comment and line.startswith(u'#'):
                comment += line[1:]
                continue
            line = line.split(u'#', 1)[0]  # Remove inline comments

            word, forms_str = (_s.strip().lower() for _s in line.split(u'~', 1))
            forms_str = forms_str.split(u'~')
            for forms_variant_str in forms_str:
                if forms_variant_str.startswith(u'noun:'):
                    noun_base = [_s.strip().lower() for _s in forms_variant_str[len(u'noun:'):].split(u'|')]
                    word_forms_dict[word].append(DictArticle(word, noun_base))
        print "Loaded %d word forms from file with comment: %s" % (len(word_forms_dict), comment)

    return word_forms_dict

def get_word_form_external(word, default=None, verbose=False):
    """
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
            word_form = get_word_form_external(word_with_ee)
            pos_e = word.find(u'е', pos_e + 1)

    return word_form or default
