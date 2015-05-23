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
    TYPE_MANUFACTURER = u"manufacturer"
    TYPE_MARKETING = u"marketing"
    TYPE_DUPLICATE = u"duplicate"  # Duplicate brands are ignored and do not export
    TYPE_DEFAULT = TYPE_MARKETING

    _brands = dict()
    """@type : dict of (unicode, Brand) """

    _all_surrogate_keys = dict()
    """@type : dict of (unicode, Brand) """

    @staticmethod
    def to_key(name):
        return (name if isinstance(name, unicode) else unicode(name, "utf-8")).strip().lower()

    @staticmethod
    def exist(name):
        exist = Brand._brands.get(Brand.to_key(name))
        return exist

    @classmethod
    def findOrCreate(cls, name):
        exist = cls.exist(name)
        return exist or cls(name)

    @staticmethod
    def all(skip_no_brand=False, skip_duplicate=True):
        """
        @rtype: list[Brand]
        """
        return sorted([b for b in Brand._brands.values()
                       if not skip_no_brand or not b.no_brand
                       if not skip_duplicate or b.type != Brand.TYPE_DUPLICATE], key=lambda b: b.name)

    def __init__(self, name=UNKNOWN_BRAND_NAME, brand_type=TYPE_DEFAULT):
        self.name = name if isinstance(name, unicode) else unicode(name, "utf-8")
        """@type: unicode"""
        if Brand.exist(self.name):
            raise Exception("Brand with name[%s] already exists" % self.name)
        Brand._brands[Brand.to_key(self.name)] = self

        # Brand type - manufacturer or marketing
        self.type = brand_type
        """@type: unicode"""

        self.manufacturers = set()
        """@type: set of (unicode)"""
        self.synonyms = []  # TODO: refactor to use set instead of list
        """@type: list[unicode]"""

        # Brand with common name which define whole own product type (like Coca-cola).
        # If generic_type is not None replace brand variant to specified common form
        self.generic_type = None
        """@type: unicode"""

        # Virtual brand flag to define product group where brand is unknown (like no-pack goods) or hidden by seller
        # Often goods with no-brand brand have hidden brand or manufacturer
        self._no_brand = False

        # Linked brands are related to this. Mainly is used for synonyms sharing.
        # Typical relation is brand<->manufacturer
        self.linked_brands = set()
        """@type: set of (unicode)"""

        # Additional non-persistent keys to represent different spellings of the brand/manufacturer name
        # Can be used for linking or lookup of the same brand with different spellings
        self.surrogate_keys = set()
        """@type: set of (unicode)"""

        self.__variants_cache = None

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

    def add_surrogate_keys(self, *keys):
        """
        Skip empty and existing keys. If primary key is passed it will be added also
        @param list[unicode] keys: surrogate keys
        @return: True if key was actually added to the set
        """
        result = False
        for key in keys:
            if not key:
                continue
            norm_key = Brand.to_key(key)
            if norm_key in self.surrogate_keys:
                continue
            brand_exists = self._all_surrogate_keys.get(norm_key)
            if brand_exists and brand_exists != self:
                raise Exception(u"Brand [%s] tries to add already registered surrogate key [%s] for brand [%s]. Merge brands first" %
                                (self.name, key, self._all_surrogate_keys[norm_key].name))
            self.surrogate_keys.add(norm_key)
            self._all_surrogate_keys[norm_key] = self

        return result

    @classmethod
    def find_by_surrogate_keys(cls, *keys):
        result = set()
        """@type : set of Brand"""
        for key in keys:
            norm_key = cls.to_key(key)
            if cls._all_surrogate_keys.has_key(norm_key):
                result.add(cls._all_surrogate_keys[norm_key])
        return result

    def get_synonyms(self, copy_related=True):
        if copy_related:
            result = [b for linked in [self] + [Brand.exist(lb) for lb in self.linked_brands if Brand.exist(lb)]
                      for b in [linked.name.lower()] + linked.synonyms]
        else:
            result = [self.name.lower()] + self.synonyms
        return list(set(result))

    def link_related(self, p_brand):
        """
        Make relationship between linked brands.
        @param Brand p_brand: to link
        """
        p_norm_key = Brand.to_key(p_brand.name)
        if p_norm_key == Brand.to_key(self.name):
            raise Exception(u"Attempt to link brand [%s] with itself" % self.name)
        if p_norm_key not in self.linked_brands:
            self.__variants_cache = None
            p_brand.__variants_cache = None
            self.linked_brands.add(p_norm_key)
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
        return ("%s [type: %s][synonyms: %s][m:%s]" % (self.name, self.type, "|".join(self.synonyms), "|".join(self.manufacturers))).encode("utf-8")

    _false_positive_brand_matches ={
        u'Абрико'.lower(): u'абрикос',
        u'Аладушкин'.lower(): u'оладушки',
        u'Добрый'.lower(): u'бодрый',
        u'Юбилейное'.lower(): u'юбилейная',
        u'Морозко'.lower(): (u'марокко', u'молоко'),
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
        u'бернли'.lower(): u'черный',
        u'коровка'.lower(): u'коробка',
        u'никола'.lower(): u'рукола',
    }
    @staticmethod
    def check_false_positive_brand_match(brand_variant, sqn_token):
        matches = Brand._false_positive_brand_matches.get(brand_variant.lower())
        return sqn_token.lower() in matches if isinstance(matches, tuple) else matches == sqn_token.lower()

    __distance_cache = dict()

    @staticmethod
    def collect_similar_tokens_as_brand_variants(s, brand_variants, variant_spelling_origin):
        """
        Iterate through all SQN tokens and try to match them with brand variants using Levenshtein distance.
        Also check false positive matches using hardcoded dictionary.
        If token similar to some of brand variants is found - add it as brand variant as well for further processing.
        Keep some explanation of this similarity in variant_spelling_origin for each token found
        @param unicode s: SQN
        @param set of (unicode) brand_variants: brand variants from replace_brand()
        @param dict of (unicode,unicode) variant_spelling_origin: simple explanation structure
        @rtype: list[unicode]
        """
        result = []
        for s_token in s.split(' '):
            if s_token in brand_variants or s_token in result:
                continue
            if len(s_token) > 4:
                similar_found = None
                for b_token0 in [bb for bb in brand_variants if len(bb) > 4 and u' ' not in bb]:
                    # TODO: implement multi-tokens
                    cache_key = u'%s~*~%s' % (b_token0, s_token)
                    if cache_key in Brand.__distance_cache:
                        dist = Brand.__distance_cache.get(cache_key)
                    else:
                        dist = distance(b_token0, s_token)
                        Brand.__distance_cache[cache_key] = dist
                    if 0 < dist <= (2 if len(s_token) > 5 else 1):
                        # TODO: Ignore (log only) if distance is 2 and both changes are immediately one after another
                        # as far as such diff produces a lot of false matches
                        if Brand.check_false_positive_brand_match(b_token0, s_token):
                            print "FOUND FALSE POSITIVE BRAND MATCH: brand variant[%s], sqn_token[%s], distance:[%d], sqn[%s]" % (
                            b_token0, s_token, dist, s)
                        else:
                            similar_found = s_token
                            variant_spelling_origin[similar_found] = u'%s~%f' % (b_token0, dist)
                        break  # Ignore all remaining brand variants because sqn token has been already matched
                if similar_found and not any(
                        Brand.check_false_positive_brand_match(b, similar_found) for b in brand_variants):
                    result.append(similar_found)
        return result

    def collect_brand_variants(self):
        """
        Collect different brand spelling variants (including translitiration) basing on brand synonyms.
        Cache variants until synonyms are changed.
        @return: set of normalized variants
        @rtype: set of (unicode)
        """
        if self.__variants_cache is None:
            brand_variants = set(map(cleanup_token_str, self.get_synonyms()))
            brand_variants.update([translit(b, "ru") for b in brand_variants if re.match(u'[a-z]', b)])

            # Add variants with spaces replaced to '-' and vice verse
            brand_variants.update(add_string_combinations(brand_variants, (u' ', u'-'), (u'-', u''), (u'-', u' '),
                  (u'е', u'ё'), (u'и', u'й'), (u'ё', u'е'), (u'й', u'и'), (u'е', u'э'), (u'э', u'е')))
            self.__variants_cache = set(brand_variants)
        else:
            brand_variants = set(self.__variants_cache)
        return brand_variants

    def replace_brand(self, s, rs=None, normalize_result=True, add_new_synonyms=True):
        """
        Replace brand name in string s to rs. Only full words will be replaced.
        Brand synonyms are iterated to check different variants.
        Quotation are treated as part of brand name substring.
        @param unicode s: original string
        @param unicode rs: replacement. If None - use brand.generic_type if not Null or space otherwise
        @return: Updated string if brand is found, original string otherwise
        @rtype unicode
        """
        if not s: return s
        if rs is None:
            rs = u"" if not self.generic_type else self.generic_type
        rs_is_blank = not re.match(u'\w', rs, re.UNICODE)
        if not rs_is_blank:
            rs = rs.strip()

        result = s

        # TODO: Amend brand_variants structure to keep explanation of variant origin (linked, translitiration, spelling, etc)
        variant_spelling_origin = dict()
        brand_variants = self.collect_brand_variants()

        similar_tokens = self.collect_similar_tokens_as_brand_variants(s, brand_variants, variant_spelling_origin)
        brand_variants.update(similar_tokens)
        if not add_new_synonyms and similar_tokens:
            # As far brand modification is switched off in this mode trace similar_tokens here
            print u"SIMILAR TOKENS FOR SQN[%s] BRAND[%s]: %s" % \
                  (s, self.name, u', '.join(u'%s(%s)' % (st, variant_spelling_origin[st]) for st in similar_tokens))

        # Start with longest brand names to avoid double processing of shortened names
        for b in sorted(brand_variants, key=len, reverse=True):
            pos = result.lower().find(b.lower())
            while pos >= 0:
                pre_char = result[pos-1] if pos > 0 else u""
                post_char = result[pos+len(b)] if pos+len(b) < len(result) else u""
                # Brand name is bounded by non-alphanum or english/russian switch (when spaces are missed)
                if not pre_char.isalnum() and (not post_char.isalnum() or (isenglish(b[-1]) and isrussian(post_char))):
                    was = result[pos:pos+len(b)]
                    if not rs_is_blank and (rs in result[:pos] or rs in result[pos+len(b):]):
                        # Replacement is already in result. Do not replicate it, use blank rs instead
                        rs = u''
                        rs_is_blank = True
                    rs2 = u' %s ' % rs
                    result = result[:pos] + rs2 + result[pos+len(b):]
                    pos += len(rs2)
                    if add_new_synonyms and self.add_synonym(was):
                        print u"NEW SYNONYM FOR BRAND %s(%s) => %s, %s" % \
                              (was, variant_spelling_origin.get(was, u""), s, str(self).decode("utf-8"))
                else:
                    if len(b) > 2:
                        print u"Suspicious string [%s] may contain brand name [%s]" % (s, b)
                    pos += len(b)
                pos = result.lower().find(b.lower(), pos)

        return cleanup_token_str(result) if normalize_result else result

    RE_MANUFACTURER_MAIN_GROUP = u'(?:\s|"|«|„)*(.+?)(?:"|»|“)*'
    RE_MANUFACTURER_PATTERN = u'^(?:Филиал\s+)?(?:С-?)?(?:АО|ЗАО|ООО|ОАО|ПАО|СП|Холдинговая\s+Компания|ХК)' + \
                              u'(?:\s+|\s*(?:(?:"|«|„)+)(?:ТК|ТПК|Компания|Фирма|ПО|МПК)\s*)?' + \
                              RE_MANUFACTURER_MAIN_GROUP + u'(?:\s*,\s*\S+)?\s*$'
    RE_MANUFACTURER_PATTERN_ENG = u'^(?:AO|ZAO|OOO|OAO|PAO)\s*(?:(?:"|«|„)+(?:TK|TPK|PO|MPK)\s*)?' + \
                                  RE_MANUFACTURER_MAIN_GROUP + u'(?:\s*,\s*\S+)?\s*$'
    __re_manufacturer_pattern = re.compile(RE_MANUFACTURER_PATTERN, re.IGNORECASE | re.UNICODE)
    __re_manufacturer_pattern_eng = re.compile(RE_MANUFACTURER_PATTERN_ENG, re.IGNORECASE | re.UNICODE)

    __manufacturer_patterns_cache = dict()
    @classmethod
    def collect_manufacturer_patterns(cls, manufacturer):
        if manufacturer in cls.__manufacturer_patterns_cache:
            return cls.__manufacturer_patterns_cache[manufacturer][:]

        patterns = re.findall(cls.__re_manufacturer_pattern, manufacturer)
        if not patterns:
            # English version
            patterns = re.findall(cls.__re_manufacturer_pattern_eng, manufacturer)
            patterns += [translit(p, "ru") for p in patterns]
        if patterns:
            patterns = add_string_combinations(patterns, (u'"', u''), (u'«', u''), (u'„', u''), (u'»', u''), (u'“', u''),
                                               (u'-', u' '), (u'-', u''), (u' ', u''), (u' ', u'-'))
        patterns += [re.sub(u'"|«|»|„|“', u'', p) for p in patterns]

        if all(manufacturer.strip().lower() != p.strip().lower() for p in patterns):
            patterns.append(manufacturer.strip())
        result = list(set(patterns))
        cls.__manufacturer_patterns_cache[manufacturer] = result[:]
        return result

    @staticmethod
    def merge_brand(main_brand, dup_brand):
        if main_brand != dup_brand:
            # Duplicated manufacturer brand was found
            if main_brand.type == Brand.TYPE_MANUFACTURER and dup_brand.type == Brand.TYPE_MANUFACTURER:
                raise Exception("Assertion failed - it's not possible to have two matched manufacturer's brands." +
                                " Duplicate: %s, Existing: %s" % (dup_brand.name, main_brand.name))
            # Merge duplicate brand to existing one
            if dup_brand.generic_type:
                raise Exception(
                    "Cannot merge non empty generic from duplicate brand: duplicate: %s, brand: %s, dup_brand: %s, generic: %s" %
                    (dup_brand.name, main_brand.name, dup_brand.name, dup_brand.generic_type))
            main_brand.add_synonym(*dup_brand.synonyms)
            main_brand.manufacturers.update(dup_brand.manufacturers)
            for link in dup_brand.linked_brands:
                linked_brand = Brand.exist(link)
                if linked_brand and linked_brand != main_brand:
                    main_brand.link_related(linked_brand)

    @classmethod
    def findOrCreate_manufacturer_brand(cls, manufacturer):
        """
        Dynamically create manufacturer's brand if it matches known manufacturer->brand patterns
        @param unicode manufacturer: manufacturer's full name
        @rtype: Brand | None
        """
        # Collect patterns and check if such brand/manufacturer is already exist
        patterns = cls.collect_manufacturer_patterns(manufacturer)
        existing_brands = cls.find_by_surrogate_keys(*patterns)
        if len(existing_brands) > 1:
            raise Exception((u"Found too many existing brands with the same surrogate keys as [%s]: %s" % (
                manufacturer, u", ".join(u'%s/%s' % (b.name, b.type) for b in existing_brands))).encode("utf-8")
            )

        # Check for known patterns than findOrCreate brand with synonyms for determined patterns
        brand = cls.findOrCreate(manufacturer) if not existing_brands else list(existing_brands)[0]
        brand.type = cls.TYPE_MANUFACTURER
        brand.manufacturers.add(manufacturer)
        brand.add_surrogate_keys(*patterns)

        # This code is for assertion of duplicated 'marketing' brands which are actually manufacturers
        # (e.g. loaded from external source with marketing type). Such 'fake' brands should be merged to
        # the main manufacturer brand and marked to ignore for further requests
        if existing_brands:
            dup_brand = Brand.exist(manufacturer)
            if dup_brand and dup_brand != brand and dup_brand.type != Brand.TYPE_DUPLICATE:  # Ignore already merged
                print "Duplicate manufacturer brand detected, trying to merge. Main: %s, Dup: %s" % (brand.name, dup_brand.name)
                cls.merge_brand(brand, dup_brand)
                # Mark duplicate brand
                dup_brand.type = Brand.TYPE_DUPLICATE

        for p in patterns:
            if p.strip().lower() != manufacturer.strip().lower():
                brand.add_synonym(p)
            brand.add_surrogate_keys(p)
            # If brand with name as pattern already exists link it.
            # Do not link other manufacturer brands because they are already related via surrogate keys (i.e. patterns)
            p_brand = cls.exist(p)
            if p_brand and p_brand != brand and p_brand.type == Brand.TYPE_MARKETING:
                brand.link_related(p_brand)
        return brand

    @staticmethod
    def to_csv(csv_filename):
        with open(csv_filename, 'wb') as f:
            f.truncate()

            header = ['name', 'type', 'no_brand', 'generic', 'synonyms', 'manufacturers', 'linked']  # 'type','linked'
            writer = csv.DictWriter(f, header)
            writer.writeheader()
            for b in Brand.all():
                if b.type == Brand.TYPE_DUPLICATE:
                    continue
                writer.writerow({'name': b.name.encode("utf-8"),
                                 'type': b.type.encode("utf-8"),
                                 'no_brand': b.no_brand,
                                 'generic': b.generic_type.encode("utf-8") if b.generic_type else None,
                                 'synonyms': u'|'.join(sorted(syn.lower() for syn in b.synonyms)).encode("utf-8"),
                                 'manufacturers': u'|'.join(sorted(b.manufacturers)).encode("utf-8"),
                                 'linked': u'|'.join(sorted(b.linked_brands)).encode("utf-8")
                                 })
        pass

    @staticmethod
    def from_csv(csv_filename):
        """
        Load brands from specified file.
        Brand records can duplicate in input. Than they will be merged. If conflicts occur Exception will be raised.
        If type field in input is manufacturer than call specific manufacturer brand routine where additional surrogate
        keys are created and linked with other brands. Therefore, all manufacturer's brands with different spellings but
        the same surrogate key will be merged in one.
        @param csv_filename:
        @return: tuple of total read and new brands created count. New brand is assumed when len(all()) changes
        @rtype: tuple(int,int)
        """
        Brand.init_standard_no_brands()

        total_count = 0
        all_len_before_load = len(Brand.all())
        link_to_actual_brand = dict()
        brands_with_links_to_fix = dict()
        with open(csv_filename, "rb") as f:
            reader = csv.reader(f)
            fields = next(reader)
            for row in reader:
                brand_row = dict(zip(fields,row))

                name = brand_row["name"].decode("utf-8")
                brand_type = brand_row.get("type", "").decode("utf-8")
                if brand_type.lower() == Brand.TYPE_MANUFACTURER.lower():
                    brand = Brand.findOrCreate_manufacturer_brand(name)
                else:
                    brand = Brand.findOrCreate(name)
                    if brand.type == Brand.TYPE_MANUFACTURER:
                        raise Exception("Attempt to load and merge manufacturer brand [%s] with different type: %s" % (name, brand_type))
                    elif brand_type and brand_type.lower() != brand.type.lower():
                        brand.type = brand_type

                if Brand.to_key(brand.name) != Brand.to_key(name):
                    # Original brand has been replaced by another manufacturer brand.
                    # However, links in file point to original brand. Keep mapping to fix links later
                    link_to_actual_brand[Brand.to_key(name)] = Brand.to_key(brand.name)

                no_brand = brand_row.get("no_brand", "False").lower() == "true"
                if not no_brand and brand.no_brand:
                    raise Exception("Try to merge brands[%s and %s] but detected no_brand conflict (was: %s, new: %s)" %
                                    (brand.name, name, brand.no_brand, no_brand))
                brand.no_brand = brand.no_brand or no_brand

                generic_s = brand_row.get("generic").decode("utf-8") if brand_row.get("generic") else None
                if generic_s and brand.generic_type and generic_s.lower() != brand.generic_type.lower():
                    raise Exception("Try to merge brands[%s and %s] but generic_type differs (was: %s, new: %s)" %
                                    (brand.name, name, brand.generic_type, generic_s))
                brand.generic_type = generic_s or brand.generic_type

                synonyms_s = brand_row.get("synonyms", "").decode("utf-8")
                if synonyms_s:
                    brand.add_synonym(*(synonyms_s.split(u'|')))

                manufacturers_s = brand_row.get("manufacturers", "").decode("utf-8")
                if manufacturers_s:
                    brand.manufacturers.update(manufacturers_s.split(u'|'))

                linked_s = brand_row.get("linked", "").decode("utf-8")
                if linked_s:
                    links = [Brand.to_key(link) for link in linked_s.split(u'|')
                             if Brand.to_key(link) not in brand.linked_brands]
                    brand.linked_brands.update(links)
                    brands_with_links_to_fix[brand.name] = brands_with_links_to_fix.get(brand.name, []) + links

                total_count += 1

            for b in brands_with_links_to_fix:
                brand = Brand.exist(b)
                links = list(brand.linked_brands)
                for i, link in enumerate(links[:]):
                    if link in link_to_actual_brand:
                        actual_brand_to_link = Brand.exist(link_to_actual_brand[link])
                        if actual_brand_to_link and actual_brand_to_link != brand:
                            brand.link_related(actual_brand_to_link)

        return total_count, len(Brand.all()) - all_len_before_load
