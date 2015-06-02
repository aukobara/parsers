# -*- coding: utf-8 -*-
from collections import defaultdict, namedtuple
import re


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

def _ensure_pymorphy():
    global __pymorph_analyzer
    import pymorphy2

    if not __pymorph_analyzer:
        __pymorph_analyzer = pymorphy2.MorphAnalyzer()

    return __pymorph_analyzer


def get_word_normal_form(word, strict=True, verbose=False):
    """
    Return first (most relevant by pymorph) normal form of specified russian word.
    @param unicode word: w
    @param bool strict: if True - process nouns and adverbs only because participle and similar has verbs
            as normal form which is useless for product parsing
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
        if p.tag.POS in ('NOUN', 'ADJF', 'ADJS', 'PRTF', 'PRTS'):
            if not p_selected:
                p_selected = p
            elif verbose and p_selected.inflect({'nomn', 'masc', 'sing'}) != p.inflect({'nomn', 'masc', 'sing'}):
                if not warning_printed:
                    print "Morphological ambiguity has been detected for word: %s (selected: %s, %s (%f))" % \
                          (word, p_selected.normal_form, p_selected.tag, p_selected.score),
                warning_printed = True
                print "\r\n%s => %s (%f)" % (p.normal_form, p.tag, p.score),
    if warning_printed: print
    p_selected = p_selected or p_variants[0]
    parse_norm = p_selected.inflect({'nomn', 'masc', 'sing'})
    if parse_norm:
        w_norm = parse_norm.word
    else:
        w_norm = p_selected.normal_form
    return w_norm if len(w_norm) > 3 else word


def is_known_word(word):
    pymorph_analyzer = _ensure_pymorphy()
    is_known = pymorph_analyzer.word_is_known(word)
    return is_known

"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
FOLLOWING ARE FUNCTIONS/TASKS TO WORK WITH EXTERNAL DICT DATA
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

class DictArticle(namedtuple('_DictArticle', 'title noun_base')):
    def __dict__(self):
        return self._asdict()

# Efremova preparations
def effr_parse(filename, out_filename=None):
    effr_dict = defaultdict(list)
    """@type: dict of (unicode, DictArticle)"""
    from os.path import getsize, abspath
    original_dict_file = abspath(filename)
    original_dict_file_size = getsize(original_dict_file)
    print "Parsing Efremova dict from %s (size: %d)" % (original_dict_file, original_dict_file_size)
    with open(filename, 'rb') as f:
        # Articles are separated by empty lines
        art = ''
        noun_bases = []
        art_count = 0
        for line in f:
            line = line.strip().decode('cp1251')
            if line:
                if not art:
                    art = line
                    if art_count % 3000 == 0: print '.',
                    art_count += 1
                    continue
                m = re.search(u'Соотносящийся по знач. с сущ.:(.+?)(?: связанный с ним.*?)?$', line, re.U)
                if m:
                    noun_list_str = m.group(1)
                    noun_bases = [noun_str.strip() for noun_str in re.findall(u'\s+([^,]+?)(?:\s+\([^)]+\))?,', noun_list_str, re.U)]
            else:
                # End of article. ready to next
                if art and noun_bases:
                    effr_dict[art] = DictArticle(art, noun_bases)
                art = u''
                noun_bases = []
        print
        print "Parsed %d terms of %d articles" % (len(effr_dict), art_count)

    if out_filename:
        print "Export parsed dict to %s" % abspath(out_filename)
        from datetime import datetime
        now = datetime.now()
        with open(out_filename, 'wb') as f:
            f.truncate()
            f.write('# Generated from "%s" (size: %d) at %s\r\n' % (original_dict_file, getsize(original_dict_file), now))
            for art, item in sorted(effr_dict.iteritems(), key=lambda _i: _i[0]):
                f.write((u'%s~noun:%s\r\n' % (art, u'|'.join(item.noun_base))).encode('utf-8'))

    return effr_dict