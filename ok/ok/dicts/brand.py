# -*- coding: utf-8 -*-
import csv
import re
from Levenshtein import distance

from transliterate import translit

from ok.dicts import cleanup_token_str, isenglish, isrussian, add_string_combinations


class Brand(object):
    """
    Base class describes Brand-Manufacturer model
    """

    UNKNOWN_BRAND_NAME = u"N/A"

    _brands = dict()
    """ @type __brands: dict of (unicode, Brand) """

    @staticmethod
    def to_key(name):
        return (name if isinstance(name, unicode) else unicode(name, "utf-8")).lower()

    @staticmethod
    def exist(name):
        exist = Brand._brands.get(Brand.to_key(name))
        """ @type exist: Brand """
        return exist

    @classmethod
    def findOrCreate(cls, name):
        exist = cls.exist(name)
        return exist or cls(name)

    @staticmethod
    def all():
        """
        @rtype: list[Brand]
        """
        return sorted(Brand._brands.values(), key=lambda b: b.name)

    def __init__(self, name=UNKNOWN_BRAND_NAME):
        self.name = name if isinstance(name, unicode) else unicode(name, "utf-8")
        if Brand.exist(self.name):
            raise Exception("Brand with name[%s] already exists" % self.name)
        Brand._brands[Brand.to_key(self.name)] = self
        self.manufacturers = set()
        self.synonyms = []  # TODO: refactor to use set instead of list
        self.generic_type = None
        self._no_brand = False

    @property
    def no_brand(self):
        return self._no_brand

    @no_brand.setter
    def no_brand(self, no_brand):
        Brand._no_brand_names_cache = None
        self._no_brand = no_brand

    _no_brand_names_cache = None
    @staticmethod
    def no_brand_names():
        if Brand._no_brand_names_cache is None:
            Brand._no_brand_names_cache = list([brand.name for brand in Brand.all() if brand.no_brand])
        return Brand._no_brand_names_cache

    def __eq__(self, other):
        return isinstance(other, Brand) and self.name == other.name

    def __str__(self):
        return ("%s [synonyms: %s][m:%s]" % (self.name, "|".join(self.synonyms), "|".join(self.manufacturers))).encode("utf-8")

    def replace_brand(self, s, rs=None, normalize_brands=True, normalize_result=True):
        """
        Replace brand name in string s to rs. Only full words will be replaced.
        Brand synonyms are iterated to check different variants.
        Quotation are treated as part of brand name substring.
        TODO: Check spelling errors and translitiration
        @param unicode s: original string
        @param unicode rs: replacement. If None - use brand.generic_type if not Null or space otherwise
        @param bool normalize_brands: if True call @cleanup_token_str for each brand and synonym
        @return: Updated string if brand is found, original string otherwise
        @rtype unicode
        """
        if not s: return s
        if rs is None:
            rs = " " if not self.generic_type else u" " + self.generic_type + u" "
        result = s

        brand_variants = [self.name] + self.synonyms
        if normalize_brands:
            brand_variants = map(cleanup_token_str, brand_variants)
            brand_variants += [translit(b.lower(), "ru") for b in brand_variants if re.match(u'[a-z]', b.lower())]

            # Add variants with spaces replaced to '-' and vice verse
            brand_variants += [b.replace(u' ', u'-') for b in brand_variants if u' ' in b] +\
                                [b.replace(u'-', u'') for b in brand_variants if u'-' in b] +\
                                [b.replace(u'-', u' ') for b in brand_variants if u'-' in b]

            for b in brand_variants:
                b_tokens = b.split(u' ', 1)
                if len(b_tokens) > 1 or len(b_tokens[0]) <= 5: continue  # TODO: implement multi-tokens
                for s_token in s.split(' '):
                    if len(s_token) > 5:
                        dist = distance(b_tokens[0].lower(), s_token.lower())
                        if 0 < dist <= 2:
                            print "FOUND SIMILAR: %s : %s in %s, brand: %s" % (b_tokens[0], s_token, s, str(self).decode("utf-8"))
                            if not any(s_token.lower() == b_i.lower() for b_i in brand_variants):
                                brand_variants.append(s_token)

        # Start with longest brand names to avoid double processing of shortened names
        for b in sorted(brand_variants, key=len, reverse=True):
            pos = result.lower().find(b.lower())
            while pos >= 0:
                pre_char = result[pos-1] if pos > 0 else u""
                post_char = result[pos+len(b)] if pos+len(b) < len(result) else u""
                if not pre_char.isalnum() and (not post_char.isalnum() or (isenglish(b[-1]) and isrussian(post_char))):  # Brand name is bounded by non-alphanum
                    was = result[pos:pos+len(b)]
                    result = result[:pos] + rs + result[pos+len(b):]
                    pos += len(rs)
                    if was.lower() != self.name.lower() and not any(was.lower() == syn.lower() for syn in self.synonyms):
                        print "NEW SYNONYM FOR BRAND %s => %s, %s" % (was, s, str(self).decode("utf-8"))
                        self.synonyms.append(was)
                else:
                    print u"Suspicious string [%s] may contain brand name [%s]" % (s, b)
                    pos += len(b)
                pos = result.lower().find(b.lower(), pos)

        return cleanup_token_str(result) if normalize_result else result

    @classmethod
    def findOrCreate_manufacturer_brand(cls, manufacturer):
        """
        Dynamically create manufacturer's brand if it matches known manufacturer->brand patterns
        @param unicode manufacturer: manufacturer's full name
        @rtype: Brand | None
        """
        brand = cls.findOrCreate(manufacturer)
        brand.manufacturers.add(manufacturer)
        # Check for known patterns than findOrCreate brand with synonyms for determined patterns
        re_main_group = u'(?:"|«)?(.+?)(?:"|»)?'
        patterns = re.findall(u'^(?:ЗАО|ООО|ОАО)\s+(?:(?:"|«)(?:ТК|ТПК|Компания|ПО|МПК)\s+)?' + re_main_group + u'(?:\s*,\s*\S+)?\s*$', manufacturer, re.IGNORECASE)
        if not patterns:
            # English version
            patterns = re.findall(u'^(?:ZAO|OOO|OAO)\s+(?:(?:"|«)(?:TK|TPK|PO|MPK)\s+)?' + re_main_group + u'(?:\s*,\s*\S+)?\s*$', manufacturer)
        if patterns:
            patterns = add_string_combinations(patterns, ('"', ''), ('-', ' '), ('-', ''))
            for p in patterns:
                p = p.replace('"', '')
                if p not in brand.synonyms:
                    brand.synonyms.append(p)
                # If brand with name as pattern already exists copy all its synonyms
                p_brand = cls.exist(p)
                if p_brand:
                    brand.synonyms += [syn for syn in p_brand.synonyms if syn not in brand.synonyms]
        return brand

    @staticmethod
    def to_csv(csvfile):
        header = ['name','no_brand','generic','synonyms','manufacturers']
        writer = csv.DictWriter(csvfile, header)
        writer.writeheader()
        for b in Brand.all():
            writer.writerow({'name': b.name.encode("utf-8"),
                             'no_brand': b.no_brand,
                             'generic': b.generic_type.encode("utf-8") if b.generic_type else None,
                             'synonyms': u'|'.join(sorted(b.synonyms)).encode("utf-8"),
                             'manufacturers': u'|'.join(sorted(b.manufacturers)).encode("utf-8")
                             })