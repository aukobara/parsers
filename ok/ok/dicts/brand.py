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
        return (name if isinstance(name, unicode) else unicode(name, "utf-8")).strip().lower()

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
    def all(skip_no_brand=False):
        """
        @rtype: list[Brand]
        """
        return sorted([b for b in Brand._brands.values() if not skip_no_brand or not b.no_brand], key=lambda b: b.name)

    def __init__(self, name=UNKNOWN_BRAND_NAME):
        self.name = name if isinstance(name, unicode) else unicode(name, "utf-8")
        if Brand.exist(self.name):
            raise Exception("Brand with name[%s] already exists" % self.name)
        Brand._brands[Brand.to_key(self.name)] = self
        self.manufacturers = set()
        self.synonyms = []  # TODO: refactor to use set instead of list
        self.generic_type = None
        self._no_brand = False
        self.linked_brands = set()

    def add_synonym(self, *syns):
        result = False
        for syn in syns:
            if not syn or Brand.to_key(syn) == Brand.to_key(self.name):
                continue
            norm_syn = syn.strip().lower()
            if any(norm_syn == s.strip().lower() for s in self.synonyms):
                continue
            self.__variants_cache = None
            self.synonyms.append(norm_syn)
            result = True

        return result

    def get_synonyms(self, copy_related=True):
        if copy_related:
            result = [b for linked in [self] + map(Brand.exist, self.linked_brands)
                      for b in [linked.name.lower()] + linked.synonyms]
        else:
            result = [self.name.lower()] + self.synonyms
        return result

    def link_related(self, p_brand):
        """
        Make relationship between linked brands.
        @param Brand p_brand: to link
        """
        if Brand.to_key(p_brand.name) not in self.linked_brands:
            self.__variants_cache = None
            p_brand.__variants_cache = None
            self.linked_brands.add(Brand.to_key(p_brand.name))
            p_brand.linked_brands.add(Brand.to_key(self.name))
        pass

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

    @staticmethod
    def init_standard_no_brands():
        Brand.findOrCreate(u"Не Бренд").no_brand = True
        Brand.findOrCreate(u"Собственное производство").no_brand = True
        Brand.findOrCreate(u"STANDARD").no_brand = True
        Brand.findOrCreate(u"Мясо").no_brand = True
        Brand.findOrCreate(u"Птица").no_brand = True
        Brand.findOrCreate(u"PL NoName").no_brand = True
        Brand.findOrCreate(u"PL NoName").add_synonym(u"PL FP")

    def __eq__(self, other):
        return isinstance(other, Brand) and self.name == other.name

    def __str__(self):
        return ("%s [synonyms: %s][m:%s]" % (self.name, "|".join(self.synonyms), "|".join(self.manufacturers))).encode("utf-8")

    _false_positive_brand_matches ={
        u'Абрико'.lower(): u'абрикос',
        u'Аладушкин'.lower(): u'оладушки',
        u'Добрый'.lower(): u'бодрый',
        u'Юбилейное'.lower(): u'юбилейная',
        u'Морозко'.lower(): u'марокко',
        u'Морозко'.lower(): u'молоко',
        u'Дальневосточный'.lower(): u'дальневосточная',
        u'Венеция'.lower(): u'венгрия',
        u'Белоручка'.lower(): u'белочка',
        u'салют'.lower(): u'салат',
        u'айсберри'.lower(): u'айсберг',
        u'рузскии'.lower(): u'русский',
        u'Черока'.lower(): u'черника',
        u'таежный'.lower(): u'темный',
        u'ОРЕХПРОМ'.lower(): u'орехом',
        u'Слада'.lower(): u'сладкая',
        u'КАРТОН'.lower(): u'картоф',
        u'ОРИМИ'.lower(): u'крими',
        u'малком'.lower(): (u'молоком',u'маком'),
        u'яблоко'.lower(): u'молоко',
        u'царская'.lower(): u'морская',
    }
    @staticmethod
    def check_false_positive_brand_match(brand_variant, sqn_token):
        matches = Brand._false_positive_brand_matches.get(brand_variant.lower())
        return sqn_token.lower() in matches if isinstance(matches, tuple) else matches == sqn_token.lower()

    __variants_cache = None
    __distance_cache = dict()
    def replace_brand(self, s, rs=None, normalize_brands=True, normalize_result=True, add_new_synonyms=True):
        """
        Replace brand name in string s to rs. Only full words will be replaced.
        Brand synonyms are iterated to check different variants.
        Quotation are treated as part of brand name substring.
        TODO: Amend brand_variants structure to keep explanation of variant origin (linked, translitiration, spelling, etc)
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

        variant_spelling_origin = dict()
        if normalize_brands:
            if self.__variants_cache is None:
                brand_variants = set(map(cleanup_token_str, self.get_synonyms()))
                brand_variants.update([translit(b, "ru") for b in brand_variants if re.match(u'[a-z]', b)])

                # Add variants with spaces replaced to '-' and vice verse
                brand_variants.update(add_string_combinations(brand_variants, (u' ',u'-'), (u'-',u''), (u'-',u' '),
                                                         (u'е',u'ё'), (u'и',u'й'), (u'ё',u'е'), (u'й',u'и')))
                self.__variants_cache = set(brand_variants)
            else:
                brand_variants = set(self.__variants_cache)

            for s_token in s.split(' '):
                if s_token in brand_variants:
                    continue
                if len(s_token) > 4:
                    similar_found = None
                    for b in brand_variants:
                        b_tokens = b.split(u' ', 1)
                        if len(b_tokens) > 1 or len(b_tokens[0]) <= 4:
                            continue  # TODO: implement multi-tokens
                        if Brand.__distance_cache.has_key(b_tokens[0] + u'~*~' + s_token):
                            dist = Brand.__distance_cache.get(b_tokens[0] + u'~*~' + s_token)
                        else:
                            dist = distance(b_tokens[0], s_token)
                            Brand.__distance_cache[b_tokens[0] + u'~*~' + s_token] = dist
                        if 0 < dist <= (2 if len(s_token) > 5 else 1):
                            if Brand.check_false_positive_brand_match(b_tokens[0], s_token):
                                print "FOUND FALSE POSITIVE BRAND MATCH: brand variant[%s], sqn_token[%s], distance:[%d], sqn[%s]" % (b_tokens[0], s_token, dist, s)
                            else:
                                similar_found = s_token
                                variant_spelling_origin[similar_found] = b_tokens[0]
                            break  # Ignore all remaining brand variants because sqn token has been already matched
                    if similar_found and not any(Brand.check_false_positive_brand_match(b, similar_found) for b in brand_variants) :
                        brand_variants.add(similar_found)
        else:
            brand_variants = set(self.get_synonyms())

        # Start with longest brand names to avoid double processing of shortened names
        for b in sorted(brand_variants, key=len, reverse=True):
            pos = result.lower().find(b.lower())
            while pos >= 0:
                pre_char = result[pos-1] if pos > 0 else u""
                post_char = result[pos+len(b)] if pos+len(b) < len(result) else u""
                # Brand name is bounded by non-alphanum
                if not pre_char.isalnum() and (not post_char.isalnum() or (isenglish(b[-1]) and isrussian(post_char))):
                    was = result[pos:pos+len(b)]
                    result = result[:pos] + rs + result[pos+len(b):]
                    pos += len(rs)
                    if add_new_synonyms and self.add_synonym(was):
                        print u"NEW SYNONYM FOR BRAND %s(%s) => %s, %s" % \
                              (was, variant_spelling_origin.get(was, u""), s, str(self).decode("utf-8"))
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
        re_main_group = u'(?:\s|"|«)?(.+?)(?:"|»)?'
        patterns = re.findall(u'^(?:Филиал\s+)?(?:С-?)?(?:ЗАО|ООО|ОАО|ПАО|СП|Холдинговая\s+Компания|ХК)\s*(?:(?:"|«)(?:ТК|ТПК|Компания|Фирма|ПО|МПК)\s*)?' + re_main_group + u'(?:\s*,\s*\S+)?\s*$', manufacturer, re.IGNORECASE)
        if not patterns:
            # English version
            patterns = re.findall(u'^(?:ZAO|OOO|OAO|PAO)\s*(?:(?:"|«)(?:TK|TPK|PO|MPK)\s*)?' + re_main_group + u'(?:\s*,\s*\S+)?\s*$', manufacturer)
        if patterns:
            patterns = add_string_combinations(patterns, (u'"', u''), (u'«', u''), (u'»', u''), (u'-', u' '), (u'-', u''))
            for p in patterns:
                p = re.sub(u'"|«|»', u'', p)
                brand.add_synonym(p)
                # If brand with name as pattern already exists copy all its synonyms
                # TODO: Also link brand with different name spelling but the same manufacturer pattern
                p_brand = cls.exist(p)
                if p_brand:
                    brand.link_related(p_brand)
        return brand

    @staticmethod
    def to_csv(csv_filename):
        header = ['name','no_brand','generic','synonyms','manufacturers']  # ,'linked'
        writer = csv.DictWriter(csv_filename, header)
        writer.writeheader()
        for b in Brand.all():
            writer.writerow({'name': b.name.encode("utf-8"),
                             'no_brand': b.no_brand,
                             'generic': b.generic_type.encode("utf-8") if b.generic_type else None,
                             'synonyms': u'|'.join(sorted(syn.lower() for syn in b.synonyms)).encode("utf-8"),
                             'manufacturers': u'|'.join(sorted(b.manufacturers)).encode("utf-8"),
                             # 'linked': u'|'.join(sorted(b.linked_brands)).encode("utf-8")
                             })
        pass

    @staticmethod
    def from_csv(csv_filename):

        Brand.init_standard_no_brands()

        # Pre-load brand synonyms
        with open(csv_filename, "rb") as f:
            reader = csv.reader(f)
            fields = next(reader)
            for row in reader:
                brand_row = dict(zip(fields,row))
                brand = Brand.findOrCreate(brand_row["name"])
                brand.no_brand = brand_row.get("no_brand", "False").lower() == "true"
                brand.generic_type = brand_row.get("generic").decode("utf-8") if brand_row.has_key("generic") else None
                synonyms_s = brand_row.get("synonyms", "").decode("utf-8")
                if synonyms_s:
                    brand.add_synonym(*(synonyms_s.split(u'|')))
                manufacturers_s = brand_row.get("manufacturers", "").decode("utf-8")
                if manufacturers_s:
                    brand.manufacturers = set(manufacturers_s.split(u'|'))
                linked_s = brand_row.get("linked", "").decode("utf-8")
                if linked_s:
                    brand.linked_brands = set(map(Brand.to_key, linked_s.split(u'|')))
        pass
