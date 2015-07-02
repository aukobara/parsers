# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function

from whoosh.analysis import Filter

from ok.dicts.term import TypeTerm


class MainFormFilter(Filter):
    is_morph = True

    def __call__(self, tokens):
        context = []
        for t in tokens:
            yield t
            if not t.stopped:
                text = t.text
                term = TypeTerm.term_dict.get_by_unicode(text)
                if term:
                    context.append(term)

        for term in context:
            wf = term.word_forms(context=context, fail_on_context=False)
            for term_form in wf or []:
                if term_form not in context:
                    t.text = term_form
                    yield t