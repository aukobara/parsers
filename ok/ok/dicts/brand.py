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

    def link_related(self, p_brand):
        """
        Make relationship between linked brands.
        Minimal implementation: copy synonyms
        TODO: Add more sophisticated link
        @param p_brand:
        @return:
        """
        self.add_synonym(p_brand.name)
        self.add_synonym(*p_brand.synonyms)
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
    }
    @staticmethod
    def check_false_positive_brand_match(brand_variant, sqn_token):
        return Brand._false_positive_brand_matches.get(brand_variant.lower()) == sqn_token.lower()

    __variants_cache = None
    __distance_cache = dict()
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

        if normalize_brands:
            if self.__variants_cache is None:
                brand_variants = set(cleanup_token_str(b) for b in [self.name.lower()] + self.synonyms)
                brand_variants.update([translit(b, "ru") for b in brand_variants if re.match(u'[a-z]', b)])

                # Add variants with spaces replaced to '-' and vice verse
                brand_variants.update(add_string_combinations(brand_variants, (u' ',u'-'), (u'-',u''), (u'-',u' '),
                                                         (u'е',u'ё'), (u'и',u'й'), (u'ё',u'е'), (u'й',u'и')))
            else:
                brand_variants = self.__variants_cache

            for s_token in s.split(' '):
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
                                print "FOUND SIMILAR: %s : %s in %s, brand: %s" % (b_tokens[0], s_token, s, self.name)
                                similar_found = s_token
                            break  # Ignore all remaining brand variants because sqn token has been already matched
                    if similar_found:
                        brand_variants.add(similar_found)
        else:
            brand_variants = set([self.name] + self.synonyms)

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
                    if self.add_synonym(was): print "NEW SYNONYM FOR BRAND %s => %s, %s" % (was, s, str(self).decode("utf-8"))
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
                p_brand = cls.exist(p)
                if p_brand:
                    brand.link_related(p_brand)
        return brand

    @staticmethod
    def to_csv(csv_filename):
        header = ['name','no_brand','generic','synonyms','manufacturers']
        writer = csv.DictWriter(csv_filename, header)
        writer.writeheader()
        for b in Brand.all():
            writer.writerow({'name': b.name.encode("utf-8"),
                             'no_brand': b.no_brand,
                             'generic': b.generic_type.encode("utf-8") if b.generic_type else None,
                             'synonyms': u'|'.join(sorted(syn.lower() for syn in b.synonyms)).encode("utf-8"),
                             'manufacturers': u'|'.join(sorted(b.manufacturers)).encode("utf-8")
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
        pass
