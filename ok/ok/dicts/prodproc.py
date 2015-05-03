# -*- coding: utf-8 -*-

# Classes and procedures to process category data from crawler's CSV output
import csv
import re
from sys import argv
from ok.items import ProductItem
import json

ATTRIBUTE_BRAND = u"Бренд:"
ATTRIBUTE_MANUFACTURER = u"Изготовитель:"
ATTRIBUTE_WEIGHT = u"Вес:"

class Brand(object):
    # TODO: Assert everything in class as unicode
    # TODO: Add single place to define default(N/A)/NoBrand

    _brands = dict()
    """ @type __brands: dict of (unicode, Brand) """

    @classmethod
    def to_key(cls, name):
        return (name if isinstance(name, unicode) else unicode(name, "utf-8")).lower()

    @classmethod
    def exist(cls, name):
        exist = cls._brands.get(cls.to_key(name))
        return exist

    @classmethod
    def findOrCreate(cls, name):
        exist = cls.exist(name)
        return exist or cls(name)

    @classmethod
    def all(cls):
        """
        @rtype: list[Brand]
        """
        return sorted(cls._brands.values(), key=lambda b: b.name)

    def __init__(self, name = "N/A"):
        self.name = name if isinstance(name, unicode) else unicode(name, "utf-8")
        self.manufacturers = set()
        self.__class__._brands[self.__class__.to_key(self.name)] = self
        self.synonyms = []
        self.generic_type = None

    def __eq__(self, other):
        return isinstance(other, Brand) and self.name == other.name

    def __str__(self):
        return ("%s [synonyms: %s][m:%s]" % (self.name, "|".join(self.synonyms), "|".join(self.manufacturers))).encode("utf-8")


def configure():
    prodcsvname = argv[1]
    toprint = "producttypes"  # default
    if len(argv) > 2:
        opt = argv[2]
        if opt == "-p" and len(argv) > 3:
            toprint = argv[3]
        else:
            raise Exception("Unknown options")

    # Pre-load brand synonyms
    Brand.findOrCreate(unicode("О'КЕЙ", "utf-8")).synonyms += [u"ОКЕЙ"]
    Brand.findOrCreate(u"Kotany").synonyms += [u"Kotanyi"]
    Brand.findOrCreate(u"Витамин").synonyms += [u"vитамин"]
    Brand.findOrCreate(u"VITAMIN").synonyms += [u"Vитамин"]
    Brand.findOrCreate(u"Мираторг").synonyms += [u"Vитамин"]
    Brand.findOrCreate(u"Садия").synonyms += [u"Мираторг"]
    Brand.findOrCreate(u"Хлебцы-Молодцы").generic_type = u"Хлебцы"
    Brand.findOrCreate(u"Хлебцы-Молодцы").synonyms += [u"Хлебцы Молодцы"]
    Brand.findOrCreate(u"Сиртаки").generic_type = u"Брынза"
    Brand.findOrCreate(u"Чупа Чупс").generic_type = u"Чупа Чупс"
    Brand.findOrCreate(u"Vitaland").synonyms += [u"Виталэнд", u"Виталанд"]
    Brand.findOrCreate(u"Активиа").synonyms += [u"Активия"]
    Brand.findOrCreate(u"PL NoName").synonyms += [u"PL FP"]
    Brand.findOrCreate(u"TM Mlekara Subotica").synonyms += [u"Mlekara Subotica"]
    Brand.findOrCreate(u"MLEKARA SABАС").synonyms += [u"Сырко"]
    Brand.findOrCreate(u"Лайме").synonyms += [u"LAIME"]
    Brand.findOrCreate(u"Laime").synonyms += [u"Лайме"]
    Brand.findOrCreate(u"Laima").synonyms += [u"Лайма"]
    Brand.findOrCreate(u"Galbani").synonyms += [u"Гальбани"]
    Brand.findOrCreate(u"Santa-Maria").synonyms += [u"Santa Maria", u"Санта Мария"]
    Brand.findOrCreate(u"Knorr").synonyms += [u"Кнорр", u"Чашка супа"]
    Brand.findOrCreate(u"Gallina Blanca").synonyms += [u"Гал.Бланка"]
    Brand.findOrCreate(u"Печем Дома").synonyms += [u"Печём дома"]
    Brand.findOrCreate(u"Gr@ce!").synonyms += [u"ГРЭЙС!"]
    Brand.findOrCreate(u"ГРЭЙС").synonyms += [u"ГРЭЙС!"]
    Brand.findOrCreate(u"Green Ray").synonyms += [u"Грин Рэй"]
    Brand.findOrCreate(u"Ciro").synonyms += [u"Cirio"]
    Brand.findOrCreate(u"Lutik").synonyms += [u"Лютик"]
    Brand.findOrCreate(u"Дмитровский молочный завод").synonyms += [u"Дмитровский МЗ", u"Дмитровская"]
    Brand.findOrCreate(u"Jon West").synonyms += [u"Джон Вест"]
    Brand.findOrCreate(u"Морской Котик").synonyms += [u"МК"]
    Brand.findOrCreate(u"STANDARD").synonyms += [u"Agama", u"Дальний Восток", u"AQUA PRODUKT", u"РРК"]  # What is it?
    Brand.findOrCreate(u"4 сезона").synonyms += [u"4Сезона"]
    Brand.findOrCreate(u"Четыре Сезона").synonyms += [u"4 Сезона"]
    Brand.findOrCreate(u"Мясо").synonyms += [u"Самсон"]  # Virtual brand
    Brand.findOrCreate(u"Heinz").synonyms += [u"Хайнц"]
    Brand.findOrCreate(u"HP").synonyms += [u"Хайнц"]
    Brand.findOrCreate(u"Агроальянс").synonyms += [u"Агро-Альянс"]
    Brand.findOrCreate(u"Рюген Фиш").synonyms += [u"Rugen Fisch"]
    Brand.findOrCreate(u"РОК-1").synonyms += [u"Аморе", u"РОК1"]
    Brand.findOrCreate(u"а'море").synonyms += [u"Аморе"]
    Brand.findOrCreate(u"Санта-Бремор").synonyms += [u"Санта Бремор"]
    Brand.findOrCreate(u"Royal Selection Belberri").synonyms += [u"Belberry"]
    Brand.findOrCreate(u"Рот Фронт").synonyms += [u"Рот-Фронт"]
    Brand.findOrCreate(u"Ложкарев").synonyms += [u"Ложкарёвъ"]
    Brand.findOrCreate(u"Бутер хлеб").synonyms += [u"Бутерхлеб"]
    Brand.findOrCreate(u"Хлебный дом").synonyms += [u"Fazer"]
    Brand.findOrCreate(u"Fazer").synonyms += [u"Фазер"]
    Brand.findOrCreate(u"Harry`s").synonyms += [u"American Sandwich"]
    Brand.findOrCreate(u"Коломенское").synonyms += [u"Коломенский"]
    Brand.findOrCreate(u"Ломайка").synonyms += [u"Коломенский"]
    Brand.findOrCreate(u"Ломайка").generic_type = u"Ломайка"
    Brand.findOrCreate(u"Dr.Schar").synonyms += [u"Schar"]
    Brand.findOrCreate(u"BLOCKBUSTER").synonyms += [u"Блокбастер"]
    Brand.findOrCreate(u"Finn Crisp").synonyms += [u"Финн Крисп"]
    Brand.findOrCreate(u"Dr.Korner").synonyms += [u"Др Корнер"]
    Brand.findOrCreate(u"Сэн Сой").synonyms += [u"Сэн-Сой"]
    Brand.findOrCreate(u"Sen Soy").synonyms += [u"Сэн-Сой"]
    Brand.findOrCreate(u"DENKER").synonyms += [u"Дэнкер"]
    Brand.findOrCreate(u"Lipton").synonyms += [u"Липтон"]
    Brand.findOrCreate(u"Greenfield").synonyms += [u"Гринфилд"]
    Brand.findOrCreate(u"Maitre").synonyms += [u"Мэтр"]
    Brand.findOrCreate(u"Tess").synonyms += [u"Тесс"]
    Brand.findOrCreate(u"Curtis").synonyms += [u"Кертис"]
    Brand.findOrCreate(u"BERNLEY").synonyms += [u"Бернли"]
    Brand.findOrCreate(u"Hillway").synonyms += [u"Хилвей"]
    Brand.findOrCreate(u"Чебуречье").synonyms += [u"Вилон"]
    Brand.findOrCreate(u"Вилон").synonyms += [u"Чебуречье"]
    Brand.findOrCreate(u"Петелино").synonyms += [u"Петелинка"]
    Brand.findOrCreate(u"Российский").synonyms += [u"Россия щедрая душа"]
    Brand.findOrCreate(u"Фабрика Крупской").synonyms += [u"Ф-ка Крупской", u"ф-ка им.Крупской"]
    Brand.findOrCreate(u"Lindt").synonyms += [u"Линдт", u"Lintd"]
    Brand.findOrCreate(u"Kinder").synonyms += [u"Киндер"]
    Brand.findOrCreate(u"Kinder").generic_type = u"Киндер"
    Brand.findOrCreate(u"Café Tasse").synonyms += [u"Кафе Тассе"]
    Brand.findOrCreate(u"Nesquick").synonyms += [u"Несквик", u"Nesquik"]
    Brand.findOrCreate(u"NESQUIK").synonyms += [u"Несквик"]
    Brand.findOrCreate(u"Nestle").synonyms += [u"Нестле", u"Несквик"]
    Brand.findOrCreate(u"Ritter Sport").synonyms += [u"Р/Спорт"]
    Brand.findOrCreate(u"Alpen Gold").synonyms += [u"Альпен Гольд"]
    Brand.findOrCreate(u"Tassimo").synonyms += [u"Тассимо"]
    Brand.findOrCreate(u"Mars").synonyms += [u"Марс", u"Милки Вей"]
    Brand.findOrCreate(u"Snickers").synonyms += [u"Сникерс"]
    Brand.findOrCreate(u'ЯЙЦА "ЯРКОVО"').synonyms += [u"Ярково", u"Роскар"]
    Brand.findOrCreate(u'ЯЙЦА "ЯРКОVО"  Столовые 1 категории (25)').synonyms += [u"Ярково", u"Роскар"]
    Brand.findOrCreate(u"Villars").synonyms += [u"Вилларс"]
    Brand.findOrCreate(u"Milka").synonyms += [u"Милка"]
    Brand.findOrCreate(u"Мясной дом БОРОДИНА").synonyms += [u"МД Бородина"]
    Brand.findOrCreate(u"Домашнее БИСТРО").synonyms += [u"Дом.Бистро"]
    Brand.findOrCreate(u"St.Dalfour").synonyms += [u"СтДальфор", u"St.Dalfou", u"St. Dalfour"]
    Brand.findOrCreate(u"Dolmio").synonyms += [u"Долмио"]
    Brand.findOrCreate(u"Dolmio").generic_type = u"Долмио"  # What is this basic type?
    Brand.findOrCreate(u"Alela").synonyms += [u"Алела", u"Алурэ"]
    Brand.findOrCreate(u"Саф-Момент").synonyms += [u"Саф Момент"]
    Brand.findOrCreate(u"Iberica").synonyms += [u"Иберика"]
    Brand.findOrCreate(u"Mamba").synonyms += [u"Мамба"]
    Brand.findOrCreate(u"FIT").synonyms += [u"ДжоФит"]
    Brand.findOrCreate(u"Bio Баланс").synonyms += [u"Био-баланс", u"Юни Милк"]
    Brand.findOrCreate(u"Balsen").synonyms += [u"Бальзен"]
    Brand.findOrCreate(u"Брест- Литовск").synonyms += [u"Брест-Литовск", u"Брест-Литовский"]
    Brand.findOrCreate(u"Альтеро").synonyms += [u"Altero"]
    Brand.findOrCreate(u"Альтеро").synonyms += [u"Altero"]
    Brand.findOrCreate(u"Австралийский Торговый Дом").synonyms += [u"АТД"]
    Brand.findOrCreate(u"Natura").synonyms += [u"Натура"]
    Brand.findOrCreate(u"DANONE").synonyms += [u"Данон"]
    Brand.findOrCreate(u"Б.Ю. Александров").synonyms += [u"Б.Ю.Александров"]
    Brand.findOrCreate(u"Anchor").synonyms += [u"ТМ Анкор", u"Анкор"]
    Brand.findOrCreate(u"ТМ Аланталь").synonyms += [u"Аланталь", u"МЗ Порховский"]
    Brand.findOrCreate(u"PRESIDENT").synonyms += [u"Президент"]
    Brand.findOrCreate(u"Margot Fromages").synonyms += [u"Margot"]
    Brand.findOrCreate(u"Almette").synonyms += [u"Альметте"]
    Brand.findOrCreate(u"VALIO").synonyms += [u"Виола", u"Валио"]
    Brand.findOrCreate(u"Viola").synonyms += [u"Виола", u"Валио"]
    Brand.findOrCreate(u"Dr.Oetker").synonyms += [u"Dr. Oetker"]
    Brand.findOrCreate(u"Mr.Сливкин").synonyms += [u"Mr. Сливкин"]
    Brand.findOrCreate(u"ОКЕАН ТРК").synonyms += [u"Океан"]
    Brand.findOrCreate(u"MacChocolate").synonyms += [u"МакШоколад"]
    Brand.findOrCreate(u"Вдохновение").synonyms += [u"Бабаевский"]
    Brand.findOrCreate(u"Бабаевский").synonyms += [u"Рот Фронт"]
    Brand.findOrCreate(u"АХА").synonyms += [u"AXA"]
    Brand.findOrCreate(u"Ясно Солнышко").synonyms += [u"ЯС"]
    Brand.findOrCreate(u"Моя Семья").synonyms += [u"МС"]
    Brand.findOrCreate(u"Фонте Аква Fonte").synonyms += [u"Fonte"]
    Brand.findOrCreate(u"ОСТАNКИНО").synonyms += [u"Останкино"]
    Brand.findOrCreate(u"Останкино").synonyms += [u"по-Останкински", u"Останкинские"]
    Brand.findOrCreate(u"Останкинское").synonyms += [u"Останкино"]
    Brand.findOrCreate(u"Рублёвский").synonyms += [u"Рублевский"]
    Brand.findOrCreate(u"колбасы и деликатесы Рублевские").synonyms += [u"Рублёвский", u"Рублевские"]
    Brand.findOrCreate(u"Клинский").synonyms += [u"Клинские МК", u"КМК"]
    Brand.findOrCreate(u"АПК \"Черкизовский\"").synonyms += [u"Черкизовский МК"]
    Brand.findOrCreate(u"АПК \"Черкизовский\"").synonyms += [u"Черкизовский МК"]
    Brand.findOrCreate(u"Merci").synonyms += [u"Мерси"]
    Brand.findOrCreate(u"Ferrero").synonyms += [u"Ферреро Роше", u"Ферреро Рошер"]
    Brand.findOrCreate(u"Cote D'or").synonyms += [u"Кот Дор"]
    Brand.findOrCreate(u"Haribo").synonyms += [u"Харибо"]
    Brand.findOrCreate(u"Toffifee").synonyms += [u"Тоффифе"]
    Brand.findOrCreate(u"FLUIDE").synonyms += [u"Флюид", u"СладКо"]
    Brand.findOrCreate(u"Kuhne").synonyms += [u"Кюне"]
    Brand.findOrCreate(u"Baleno").synonyms += [u"Балено"]
    Brand.findOrCreate(u"ПРОДУКТЫ ОТ ИЛЬИНОЙ").synonyms += [u"От Ильиной"]
    Brand.findOrCreate(u"Колпинский, Ильина").synonyms += [u"От Ильиной"]
    Brand.findOrCreate(u"Меридиан").synonyms += [u"Мирамар"]
    Brand.findOrCreate(u"Приазовская").synonyms += [u"Троекурово"]
    Brand.findOrCreate(u"Биг Ланч").synonyms += [u"БигЛанч"]
    Brand.findOrCreate(u"BIGBON").synonyms += [u"БигБон"]
    Brand.findOrCreate(u"DELICADOS").synonyms += [u"Деликадос"]
    Brand.findOrCreate(u"Меркатус Напитки из Черноголовки").synonyms += [u"Напитки из Черноголовки"]
    Brand.findOrCreate(u"Frukto").synonyms += [u"Фруктомания"]
    Brand.findOrCreate(u"Alaeddin").synonyms += [u"Алладин"]
    Brand.findOrCreate(u"Тысяча Озер").synonyms += [u"Тысяча озёр"]
    Brand.findOrCreate(u"3 Glocken").synonyms += [u"3Glocken"]
    Brand.findOrCreate(u"MacCoffee").synonyms += [u"МакКофе"]
    Brand.findOrCreate(u"MacCoffee").generic_type = u"Кофе"
    Brand.findOrCreate(u"Саратовский").synonyms += [u"Саратововский"]
    Brand.findOrCreate(u"ITLV").synonyms += [u"ИТЛВ"]
    Brand.findOrCreate(u"Рузское молоко").synonyms += [u"Рузское", u"Рузский"]
    Brand.findOrCreate(u"Из Вологды").synonyms += [u"Северное молоко"]
    Brand.findOrCreate(u"Омский завод плавленых сыров").synonyms += [u"Ичалковское"]
    Brand.findOrCreate(u"Ичалки").synonyms += [u"Ичалковский"]
    Brand.findOrCreate(u"Очаково").synonyms += [u"Очаковский"]
    Brand.findOrCreate(u"Первая Свежесть").synonyms += [u"Элинар"]
    Brand.findOrCreate(u"Надежда КФ").synonyms += [u"Коровалетта Молоконти"]
    Brand.findOrCreate(u"Доль Ким").synonyms += [u"ДольКим"]
    Brand.findOrCreate(u"ГИАГИНСКИЙ молзавод").synonyms += [u"Гиагинский МЗ"]
    Brand.findOrCreate(u"Garcia Baquero").synonyms += [u"Гарсия Бакеро"]
    Brand.findOrCreate(u"Сыры \"Красногвардейские\"").synonyms += [u"Адыгея КМЗ", u"КМЗ"]
    Brand.findOrCreate(u"Arla").synonyms += [u"Арла", u"Апетина"]
    Brand.findOrCreate(u"Apetina").synonyms += [u"Апетина"]
    Brand.findOrCreate(u"Locatelli").synonyms += [u"Локателли"]
    Brand.findOrCreate(u"Савушкин").synonyms += [u"101 Зерно"]
    Brand.findOrCreate(u"Emmi").synonyms += [u"Эмми", u"Эмми деликат"]
    Brand.findOrCreate(u"4LIFE").synonyms += [u"4 Life"]
    Brand.findOrCreate(u"DROGHERIA E ALIMENTARI").synonyms += [u"Drogheria"]
    Brand.findOrCreate(u"Фруктовый  сад").synonyms += [u"Фруктовый Сад"]
    Brand.findOrCreate(u"J-7").synonyms += [u"J7"]
    Brand.findOrCreate(u"ВБД J-7 Фрустайл").synonyms += [u"J7"]
    Brand.findOrCreate(u"Tropicana").synonyms += [u"Тропикана"]
    Brand.findOrCreate(u"Coca-Cola").synonyms += [u"Кока Кола"]
    Brand.findOrCreate(u"Coca-Cola").generic_type = u"Coca-Cola"
    Brand.findOrCreate(u"7-UP").synonyms += [u"Севен Ап"]
    Brand.findOrCreate(u"7-UP").generic_type = u"7-UP"
    Brand.findOrCreate(u"Морозко").synonyms += [u"ОКЕЙ", u"Цезарь"]
    Brand.findOrCreate(u"Звездный").synonyms += [u"Морозко"]
    Brand.findOrCreate(u"Франко Оллиани").synonyms += [u"Olliani"]
    Brand.findOrCreate(u"Maestro de Oliva").synonyms += [u"Маэстро де Олива"]
    Brand.findOrCreate(u"Нутелла").synonyms += [u"Nutella"]
    Brand.findOrCreate(u"Финети").synonyms += [u"Финетти"]
    Brand.findOrCreate(u"Белевская пастила").synonyms += [u"Белевская"]
    Brand.findOrCreate(u"Белевская пастила").synonyms += [u"Белевская"]
    Brand.findOrCreate(u"Hame").synonyms += [u"Хаме"]
    Brand.findOrCreate(u"Равиолло").synonyms += [u"Снежная страна"]
    Brand.findOrCreate(u"Белебеевский МК").synonyms += [u"Белебей"]

    # Manufacturer's brands
    Brand.findOrCreate(u"ООО \"Эхо\"").synonyms += [u"Белоручка"]
    Brand.findOrCreate(u"Arla Foods amba").synonyms += [u"Арла"]
    Brand.findOrCreate(u"Citterio").synonyms += [u"Читтерио"]
    Brand.findOrCreate(u"DP \"Artemsil`\"").synonyms += [u"Артем"]
    Brand.findOrCreate(u"Dolceria Alba S.r.l").synonyms += [u"Laime"]
    Brand.findOrCreate(u"Frozen Fish International GmbH").synonyms += [u"Iglo"]
    Brand.findOrCreate(u"OOO \"TPK \"VILON\"").synonyms += [u"Сытоедов"]
    Brand.findOrCreate(u"RONGGHENG SANY FOODSTUFF Co. Ltd").synonyms += [u"NORTON"]
    Brand.findOrCreate(u"Tulip").synonyms += [u"Tulip"]
    Brand.findOrCreate(u"WORKSHOP I SEAPRODEX, Вьетнам").synonyms += [u"Emborg"]
    Brand.findOrCreate(u'ЗАО "БРПИ"').synonyms += [u"Баскин Роббинс"]
    Brand.findOrCreate(u'ЗАО "Балтийский берег"').synonyms += [u"Балтийский Берег"]
    Brand.findOrCreate(u'ЗАО "Дедовский хлеб"').synonyms += [u"Дедовский хлеб"]
    Brand.findOrCreate(u'ЗАО "ИТА Северная Компания"').synonyms += [u"СК"]
    Brand.findOrCreate(u'ЗАО "Краснобор", Россия').synonyms += [u"Краснобор"]
    Brand.findOrCreate(u'ЗАО "Приосколье", Россия').synonyms += [u"ГВУ Приосколье"]
    Brand.findOrCreate(u'ЗАО "Русская рыбная компания", Россия').synonyms += [u"РРК"]
    Brand.findOrCreate(u'ЗАО "Русское море"').synonyms += [u"Русское море"]
    Brand.findOrCreate(u'ЗАО "СевероВосточная компания", Россия').synonyms += [u"PLESK"]
    Brand.findOrCreate(u'ОАО "Березовский мясоконсервный комбинат"').synonyms += [u"Береза"]
    Brand.findOrCreate(u'ОАО "Маслосырзавод "Порховский"').synonyms += [u"МЗ Порховский"]
    Brand.findOrCreate(u'ООО МОРОЗКО').synonyms += [u"La Trattoria"]
    Brand.findOrCreate(u'ООО "МОРОЗКО"').synonyms += [u"Морозко Green"]
    Brand.findOrCreate(u'ООО "Элинар-Бройлер"').synonyms += [u"Элинар"]
    Brand.findOrCreate(u'ООО "Элинар-Бройлер", Россия').synonyms += [u"Элинар"]



    return (prodcsvname, toprint)


def parse_pfqn(pfqn):
    """
    Parse Full Product Name and return name parts: type, brand, weight, fat, etc
    TODO: Some pfqn can have multiple entries, use list/dict instead of tuple
    @param unicode pfqn: Full Product Name
    @rtype: (unicode, unicode, unicode, unicode)
    """
    pfqn = pfqn.lower()
    pre = u'(?:\s|\.|,|\()'  # prefix can be consumed by re parser and must be returned in sub - must be always 1st Match
    post = u'(?=\s|$|,|\.|\)|/)'  # post is predicate and isn't consumed by parser. but must start immediately after term group

    def _add_match(ll, match):
        _pre = match.group(1)
        _m = match.group(2)
        ll[0] = (ll[0] + u" + " if ll[0] else "") + _m.strip()
        return _pre

    # weight - if has digit should be bounded by non-Digit, if has no digit - than unit only is acceptable but as token
    wl = [u""]
    pfqn = re.sub(u'(\D)('
                u'(?:\d+(?:шт|пак)?(?:х|\*|x|/))?'
                u'(?:\d+(?:[\.,]\d+)?\s*)'
                u'(?:кг|г|л|мл|гр)\.?'
                u'(?:(?:х|\*|x|/)\d+(?:\s*шт)?)?'
                u')' + post,
           lambda g: _add_match(wl, g),
           pfqn
           )
    if not wl[0]:
        pfqn = re.sub( u'(\D' + pre + u')((?:кг|г|л|мл|гр)\.?)' + post,
                        lambda g: _add_match(wl, g),
                        pfqn )
    # fat
    fl=[u""]
    mdzh = u'(?:\s*(?:с\s)?м\.?д\.?ж\.? в сух(?:ом)?\.?\s?вещ(?:-|ест)ве\s*|\s*массовая доля жира в сухом веществе\s*)?'
    pfqn = re.sub( u'(' + pre + u')(' + mdzh + u'(?:\d+(?:[\.,]\d+)?%?-)?\d+(?:[\.,]\d+)?\s*%(?:\s*жирн(?:\.|ости)?)?' + mdzh + u')' + post,
                   lambda g: _add_match(fl, g), pfqn )
    # pack
    pl=[u""]
    pfqn = re.sub( u'(' + pre + u')'
                  u'(т/пак|ж/б|ст/б|м/у|с/б|ст/бут|пл/б|пл/бут|пэтбутылка|пл|кор\.?|\d*\s*пак\.?|\d+\s*таб|\d+\s*саше|\d+\s*пир(?:\.|амидок)?|(?:\d+\s*)?шт\.?|упак\.?|уп\.?|в/у|п/э|жесть|'
                  u'стакан|ванночка|в\sванночке|дой-пак|дой/пак|пюр-пак|пюр\sпак|зип|зип-пакет|д/пак|п/пак|пл\.упаковка|пэт|пакет|туба|ведро|бан|лоток|фольга|фас(?:ованные)?|н/подл\.?|ф/пакет|0[.,]5|0[.,]75|0[.,]33)' + post,
                   lambda g: _add_match(pl, g), pfqn )
    return wl[0], fl[0], pl[0], pfqn


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


def replace_brand(s, brand, rs):
    """
    Replace brand name in string s to rs. Only full words will be replaced.
    Brand synonyms are iterated to check different variants.
    Quotation are treated as part of brand name substring.
    TODO: Check spelling errors and translitiration
    @param unicode s: original string
    @param Brand brand: brand entity with synonyms
    @param unicode rs: replacement
    @return: Updated string if brand is found, original string otherwise
    @rtype unicode
    """
    if not s: return s
    brand_variants = [brand.name] + brand.synonyms
    result = s
    # Start with longest brand names to avoid double processing of shortened names
    for b in sorted(brand_variants, key=len, reverse=True):
        pos = result.lower().find(b.lower())
        while pos >= 0:
            pre_char = result[pos-1] if pos > 0 else u""
            post_char = result[pos+len(b)] if pos+len(b) < len(result) else u""
            if not pre_char.isalnum() and (not post_char.isalnum() or (isenglish(b[-1]) and isrussian(post_char))):  # Brand name is bounded by non-alphanum
                result = result[:pos] + rs + result[pos+len(b):]
                pos += len(rs)
            else:
                print (u"Suspicious string [%s] may contain brand name [%s]" % (s, b))
                pos += len(b)
            pos = result.lower().find(b.lower(), pos)

    return result


def cleanup_token_str(s):
    """
    Cleanup one-line string from non-label symbols - colon, quotes, periods etc
    Replace multi-spaces to single space. Strip
    @param unicode s: one-line string
    @rtype: unicode
    """
    return re.sub(u'(?:\s|"|,|\.|«|»|\(|\))+', u' ', s).strip()


if __name__ == '__main__':
    (prodcsvname, toprint) = configure()

    types = dict()
    """ @type types: dict of (unicode, dict[str, unicode]) """
    weights = dict()
    fats = dict()
    packs = dict()
    with open(prodcsvname, "rb") as f:
        reader = csv.reader(f)
        fields = next(reader)
        for row in reader:
            prodrow = dict(zip(fields, row))
            item = ProductItem(prodrow)
            pfqn = unicode(item["name"], "utf-8")

            product_manufacturer = None
            if item.get("details"):
                details = json.loads(item["details"])
                """ @type details: dict of (unicode, unicode) """

                brand = Brand.findOrCreate(details.get(ATTRIBUTE_BRAND, "N/A"))

                product_manufacturer = details.get(ATTRIBUTE_MANUFACTURER)
                if product_manufacturer:
                    brand.manufacturers.add(product_manufacturer)
            else:
                brand = Brand.findOrCreate(u"N/A")

            (weight, fat, pack, sqn) = parse_pfqn(pfqn)
            def __fill_fqn_dict(d, item):
                for k in item.split(u" + "): d[k] = d.get(k, 0) + 1
            __fill_fqn_dict(weights, weight)
            __fill_fqn_dict(fats, fat)
            __fill_fqn_dict(packs, pack)

            known_brands = [brand]
            if product_manufacturer:
                manufacturer_brand = Brand.exist(product_manufacturer)
                if manufacturer_brand and manufacturer_brand != brand:
                    # Consider manufacturer as brand - replace its synonyms
                    known_brands.append(manufacturer_brand)

            sqn_without_brand = sqn
            for ibrand in known_brands:
                if ibrand.name != u"N/A":
                    sqn_without_brand = replace_brand(sqn_without_brand, ibrand,
                                                  " " if not ibrand.generic_type else u" " + ibrand.generic_type + u" ")

            types[pfqn] = dict(weight=weight, fat=fat, pack=pack,
                               brand=brand.name,
                               sqn=cleanup_token_str(sqn_without_brand),
                               brand_detected=sqn != sqn_without_brand,
                               product_manufacturer=product_manufacturer)

    if toprint == "brands":
        manufacturers = dict()
        """ @type manufacturers: dict of (unicode, list[unicode]) """
        for b in Brand.all():
            print b
            for m in b.manufacturers:
                manufacturers[m] = manufacturers.get(m, [])
                manufacturers[m].append(b.name)
                manufacturers[m] += map(lambda s: "~"+s, b.synonyms)
        print "Total brands: %d" % len(Brand.all())
        print
        for m, b in sorted(manufacturers.iteritems(), key=lambda t:t[0]):
            print "%s [%s]" % (m, "|".join(b))
            for linked_m in [im for ib in b for im in Brand.findOrCreate(ib).manufacturers
                             if im != m and ib != u"Не Бренд" and ib != u"PL NoName" and (ib != u"О'КЕЙ" or m == u"ООО \"О'КЕЙ\"")]:
                print "    ==> %s [%s]" % (linked_m, "|".join(manufacturers[linked_m]))
        print "Total manufacturers: %d" % len(manufacturers)

    elif toprint == "producttypes":
        ptypes_count = 0
        nobrand_count = 0
        # for t, d in sorted(types.iteritems(), key=lambda t: t[1]["sqn"].split(" ", 1)[0]):
        for t, d in sorted(types.iteritems(), key=lambda t: t[1]["product_manufacturer"]):
            if d["product_manufacturer"] and not d["brand_detected"] and (d["brand"] == u"Не Бренд"
                    or d["brand"] == u"Собственное производство"
                    or d["brand"] == u"Мясо"
                    or d["brand"] == u"Птица"):
                print '%s   => brand: %s, prod_man: %s, weight: %s, fat: %s, pack: %s, fqn: %s' % \
                      (d["sqn"], d["brand"], d["product_manufacturer"], d["weight"], d["fat"], d["pack"], t)
                nobrand_count += 1
            elif not d["brand_detected"]:
#                print '%s   => brand: %s, weight: %s, fat: %s, pack: %s, fqn: %s' % \
#                      (d["sqn"], d["brand"], d["weight"], d["fat"], d["pack"], t)
                ptypes_count += 1
        print
        print "Total product types: %d [notintype: %d, nobrand: %d]" % (len(types), ptypes_count, nobrand_count)
        print

    elif toprint == "typetuples":
        types2 = dict()
        for t, d in sorted(types.iteritems(), key=lambda t: t[1]["sqn"].split(" ", 1)[0]):
            words = re.split(u'\s+', d["sqn"])
            first_word = words.pop(0)
            buf = ''
            for w in words:
                if w:
                    if w == u'в' or w == u'с' or w == u'со' or w == u'из' or w == u'для' or w == u'и' or w == u'на':
                        buf = w  # join proposition to the next word
                        continue
                    w = buf + u' ' + w if buf else w
                    types2[(first_word, w)] = types2.get((first_word, w), 0) + 1
                    buf = u''

        num_tuples = dict()
        for t, c in sorted(types2.iteritems(), key=lambda k: types2[k[0]], reverse=True):
            print "Tuple %s + %s: %d" % (t[0], t[1], c)
            num_tuples[c] = num_tuples.get(c, 0) + 1
        print "Total tuples: %d" % len(types2)
        for num in sorted(num_tuples.iterkeys(), reverse=True):
            print "    %d: %d" % (num, num_tuples[num])

    elif toprint == "weights":
        for dict_i in (weights, fats, packs):
            print "#" * 20
            print "\r\n".join(["%s [%d]" % (k, v) for k,v in sorted(dict_i.iteritems(), key=lambda t:t[1], reverse=True)])

        print "NO-WEIGHT Product Types " + "=" *60
        c = 0
        for t, d in types.iteritems():
            if not d["weight"]:
                print t,
                print '     => fat: %s, pack: %s' % (d["fat"], d["pack"]) if d["fat"] or d["pack"] else ""
                c+=1
        print "Total: %d" % c

    else:
        raise Exception("Unknown print type [%s]" % toprint)


