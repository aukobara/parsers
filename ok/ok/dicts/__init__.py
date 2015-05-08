# -*- coding: utf-8 -*-

"""
Basic text processing utils
"""
import re


def cleanup_token_str(s, ext_symbols=None):
    """
    Cleanup one-line string from non-label symbols - colon, quotes, periods etc
    Replace multi-spaces to single space. Strip
    @param unicode s: one-line string
    @param list[unicode] ext_symbols: list of additional symbols to clean
    @rtype: unicode
    """
    ext = '|'.join(ext_symbols) if ext_symbols else None
    return re.sub(u'(?:\s|"|,|\.|«|»|“|”|\(|\)|\?|\+' + ('|' + ext if ext else '') + ')+', u' ', s).strip()


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
            for r in repl:
                p1 = p.replace(*r)
                if p1 != p:
                    break
            if p1 not in result:
                result.append(p1)
                p_modified = True
    return result


def remove_nbsp(s):
    return None if s is None else s.replace(u'\u00a0', ' ') if isinstance(s, unicode) else s.replace('\xa0', ' ')