# -*- coding: utf-8 -*-

import csv
import re
import json
from sys import argv

from ok.items import ProductItem
from ok.dicts import cleanup_token_str
from ok.dicts.brand import Brand
from ok.dicts.catsproc import Cats


ATTRIBUTE_BRAND = u"Бренд:"
ATTRIBUTE_MANUFACTURER = u"Изготовитель:"
ATTRIBUTE_WEIGHT = u"Вес:"

def configure():
    prodcsvname = argv[1]
    toprint = "producttypes"  # default
    catcsvname = None # Don't pre-load categories by default
    brandscsvname = None # Don't save brands by default
    while len(argv) > 2:
        opt = argv.pop(2)
        if opt == "-p" and len(argv) > 2:
            toprint = argv.pop(2)
        elif opt == "-c" and len(argv) > 2:
            catcsvname = argv.pop(2)
        elif opt == "-out-brands-csv" and len(argv) > 2:
            brandscsvname = argv.pop(2)
        else:
            raise Exception("Unknown options")

    # Pre-load brand synonyms
    Brand.findOrCreate(u"Не Бренд").no_brand = True
    Brand.findOrCreate(u"Собственное производство").no_brand = True
    Brand.findOrCreate(u"STANDARD").no_brand = True
    Brand.findOrCreate(u"Мясо").no_brand = True
    Brand.findOrCreate(u"Птица").no_brand = True
    Brand.findOrCreate(u"PL NoName").no_brand = True
    Brand.findOrCreate(u"PL NoName").synonyms += [u"PL FP"]

    Brand.findOrCreate(u"О'КЕЙ").synonyms += [u"ОКЕЙ"]
    Brand.findOrCreate(u"Kotany").synonyms += [u"Kotanyi"]
    Brand.findOrCreate(u"Витамин").synonyms += [u"vитамин"]
    Brand.findOrCreate(u"VITAMIN").synonyms += [u"Vитамин"]
    Brand.findOrCreate(u"Хлебцы-Молодцы").generic_type = u"Хлебцы"
    Brand.findOrCreate(u"Хлебцы-Молодцы").synonyms += [u"Хлебцы Молодцы"]
    Brand.findOrCreate(u"Сиртаки").generic_type = u"Брынза"
    Brand.findOrCreate(u"Чупа Чупс").generic_type = u"Чупа Чупс"
    Brand.findOrCreate(u"Vitaland").synonyms += [u"Виталэнд", u"Виталанд"]
    Brand.findOrCreate(u"Активиа").synonyms += [u"Активия"]
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
    Brand.findOrCreate(u"4 сезона").synonyms += [u"4Сезона"]
    Brand.findOrCreate(u"Четыре Сезона").synonyms += [u"4 Сезона"]
    Brand.findOrCreate(u"Heinz").synonyms += [u"Хайнц"]
    Brand.findOrCreate(u"HP").synonyms += [u"Хайнц"]
    Brand.findOrCreate(u"Агроальянс").synonyms += [u"Агро-Альянс"]
    Brand.findOrCreate(u"Рюген Фиш").synonyms += [u"Rugen Fisch"]
    Brand.findOrCreate(u"Санта-Бремор").synonyms += [u"Санта Бремор", u"Бухта Изобилия"]
    Brand.findOrCreate(u"Royal Selection Belberri").synonyms += [u"Belberry"]
    Brand.findOrCreate(u"Рот Фронт").synonyms += [u"Рот-Фронт"]
    Brand.findOrCreate(u"Ложкарев").synonyms += [u"Ложкарёвъ", u"Чудо-малыши", u"Шельф", u"Любимые"]
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
    Brand.findOrCreate(u"Акбар").synonyms += [u"Бернли", u"English Classic"]
    Brand.findOrCreate(u"Hillway").synonyms += [u"Хилвей"]
    Brand.findOrCreate(u"Чебуречье").synonyms += [u"Вилон"]
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
    Brand.findOrCreate(u"VALIO").synonyms += [u"Виола", u"Валио", u"Гефилус", u"Gefilus"]
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
    Brand.findOrCreate(u"Останкинский молочный комбинат").synonyms += [u"Останкино", u"Останкинское", u"по-Останкински", u"Останкинские", u"Останкинская", u"Останкинский"]
    Brand.findOrCreate(u"Останкино").synonyms += Brand.findOrCreate(u"Останкинский молочный комбинат").synonyms
    Brand.findOrCreate(u"Останкинское").synonyms += Brand.findOrCreate(u"Останкинский молочный комбинат").synonyms
    Brand.findOrCreate(u"Рублёвский").synonyms += [u"Рублевский"]
    Brand.findOrCreate(u"колбасы и деликатесы Рублевские").synonyms += [u"Рублёвский", u"Рублевские"]
    Brand.findOrCreate(u"Клинский").synonyms += [u"Клинские МК", u"КМК"]
    Brand.findOrCreate(u"АПК \"Черкизовский\"").synonyms += [u"Черкизовский МК"]
    Brand.findOrCreate(u"Merci").synonyms += [u"Мерси"]
    Brand.findOrCreate(u"Ferrero").synonyms += [u"Ферреро Роше", u"Ферреро Рошер"]
    Brand.findOrCreate(u"Cote D'or").synonyms += [u"Кот Дор"]
    Brand.findOrCreate(u"Haribo").synonyms += [u"Харибо"]
    Brand.findOrCreate(u"Toffifee").synonyms += [u"Тоффифе"]
    Brand.findOrCreate(u"FLUIDE").synonyms += [u"Флюид", u"СладКо"]
    Brand.findOrCreate(u"Kuhne").synonyms += [u"Кюне"]
    Brand.findOrCreate(u"Baleno").synonyms += [u"Балено"]
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
    Brand.findOrCreate(u"Рузское молоко").synonyms += [u"Рузское", u"Рузский", u"Рузская", u"Рузские"]
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
    Brand.findOrCreate(u"Морозко").synonyms += [u"ОКЕЙ", u"Цезарь", u"Морозко Green", u"La Trattoria"]
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
    Brand.findOrCreate(u"Bonaqua").synonyms += [u"БонАква"]
    Brand.findOrCreate(u"Sprite").synonyms += [u"Спрайт"]
    Brand.findOrCreate(u"Fanta").synonyms += [u"Фанта"]
    Brand.findOrCreate(u"Schweppes").synonyms += [u"Швеппс"]
    Brand.findOrCreate(u"Nescafe").synonyms += [u"Нескафе", u"Нескафе Голд"]
    Brand.findOrCreate(u"Jacobs").synonyms += [u"Якобс", u"Якобс Монарх"]
    Brand.findOrCreate(u"Русская нива").synonyms += [u"Частная галерея"]
    Brand.findOrCreate(u"Maggi").synonyms += [u"Смесь Магги на второе", u"Магги"]
    Brand.findOrCreate(u"Maggi").generic_type = u"Приправа"
    Brand.findOrCreate(u"Петрохолод").synonyms += [u"Идеальная пара"]
    Brand.findOrCreate(u"Костровок").synonyms += [u"Идея на закуску"]
    Brand.findOrCreate(u'Tchibo').synonyms += [u"Чибо", u"Эксклюзив", u"Голд Селекшен", u"Майлд", u"Интенс"]
    Brand.findOrCreate(u'Tchibo Manufacturing Poland Sp.z.o.o.').synonyms += [u'Tchibo'] + Brand.findOrCreate(u'Tchibo').synonyms

    # Manufacturer's brands
    Brand.findOrCreate(u"ООО \"Эхо\"").synonyms += [u"Белоручка"]
    Brand.findOrCreate(u"Arla Foods amba").synonyms += [u"Арла"]
    Brand.findOrCreate(u"Citterio").synonyms += [u"Читтерио"]
    Brand.findOrCreate(u"DP \"Artemsil`\"").synonyms += [u"Артем"]
    Brand.findOrCreate(u"Dolceria Alba S.r.l").synonyms += [u"Laime"]
    Brand.findOrCreate(u"Frozen Fish International GmbH").synonyms += [u"Iglo"]
    Brand.findOrCreate(u"Вилон").synonyms += [u"Чебуречье", u"Вкусный Суп", u"Обожамс", u"Сытоедов"]
    Brand.findOrCreate(u"VILON").synonyms += [u"Вилон"] + Brand.findOrCreate(u"Вилон").synonyms
    Brand.findOrCreate(u"Tulip").synonyms += [u"Tulip"]
    Brand.findOrCreate(u"WORKSHOP I SEAPRODEX, Вьетнам").synonyms += [u"Emborg"]
    Brand.findOrCreate(u"Тай Юнион Фрозен Продактс Паблик").synonyms += [u"Emborg"]
    Brand.findOrCreate(u'ЗАО "Дедовский хлеб"').synonyms += [u"Дедовский хлеб"]
    Brand.findOrCreate(u'ЗАО "ИТА Северная Компания"').synonyms += [u"СК"]
    Brand.findOrCreate(u'ЗАО "Краснобор", Россия').synonyms += [u"Краснобор"]
    Brand.findOrCreate(u'ЗАО "Приосколье", Россия').synonyms += [u"ГВУ Приосколье"]
    Brand.findOrCreate(u'ЗАО "Русская рыбная компания", Россия').synonyms += [u"РРК"]
    Brand.findOrCreate(u'ЗАО "Русское море"').synonyms += [u"Русское море"]
    Brand.findOrCreate(u'ЗАО "СевероВосточная компания", Россия').synonyms += [u"PLESK"]
    Brand.findOrCreate(u'ОАО "Березовский мясоконсервный комбинат"').synonyms += [u"Береза"]
    Brand.findOrCreate(u'ОАО "Маслосырзавод "Порховский"').synonyms += [u"МЗ Порховский"]
    Brand.findOrCreate(u'ООО "Элинар-Бройлер"').synonyms += [u"Элинар"]
    Brand.findOrCreate(u'ООО "Элинар-Бройлер", Россия').synonyms += [u"Элинар"]
    Brand.findOrCreate(u'Талосто-Продукты').synonyms += [u"Мастерица", u"Талосто", u"Талосто-3000", u"Ля Фам", u"Без хлопот", u'Венеция']
    Brand.findOrCreate(u'Талосто-3000').synonyms += [u"Талосто-Продукты"] + Brand.findOrCreate(u'Талосто-Продукты').synonyms
    Brand.findOrCreate(u'Проморе').synonyms += [u"NORTON"]
    Brand.findOrCreate(u"RONGGHENG SANY FOODSTUFF Co. Ltd").synonyms += [u"NORTON"]
    # Implicit brand - neither defined as explicit brand but used in no-brand products
    Brand.findOrCreate(u"Не Бренд").manufacturers.add(u"Белая Дача")
    Brand.findOrCreate(u"Белая Дача").synonyms += [u"Белая Дача"]
    Brand.findOrCreate(u"Пчеловод").synonyms += [u"Дальневосточный", u"Алтайский", u"Таёжный"]
    Brand.findOrCreate(u"Агама Роял Гринланд").synonyms += [u"Бухта изобилия", u"Agama", u"Агама"]
    Brand.findOrCreate(u"Лагуна Койл").synonyms += [u"Русский Холод", u"СССР", u"Юбилейное", u"Любимое", u"Юпитер Гигант", u"Лакомка", u"Энерго"]
    Brand.findOrCreate(u"Мясной стандарт").synonyms += [u"Дары Артемиды", u"Максума"]
    Brand.findOrCreate(u"Мираторг").synonyms += [u"Vитамин", u"Мирандия", u"GurMama", u"Садия"]
    Brand.findOrCreate(u"Мираторг-Запад").synonyms += [u"Мираторг"] + Brand.findOrCreate(u"Мираторг").synonyms
    Brand.findOrCreate(u"Садия").synonyms += [u"Мираторг"]
    Brand.findOrCreate(u"Вичюнай-Русь").synonyms += [u"VICI", u"Любо есть"]
    Brand.findOrCreate(u"Вичюнай Русь").synonyms += [u"Вичюнай-Русь"] + Brand.findOrCreate(u"Вичюнай-Русь").synonyms
    Brand.findOrCreate(u"Белорусский вкус").synonyms += [u"Мясной Двор"]
    Brand.findOrCreate(u"Невские сыры").synonyms += [u"ГОСТ 52253"]
    Brand.findOrCreate(u"Мясная империя").synonyms += [u"Московский", u"ГОСТ"]
    Brand.findOrCreate(u"Золотой Петушок").synonyms += [u"ЗП", u"Золотой Петушок", u'Добротный Продукт']
    Brand.findOrCreate(u"Продукты питания Комбинат").synonyms += Brand.findOrCreate(u"Золотой Петушок").synonyms
    Brand.findOrCreate(u"Мясокомбинат Всеволожский").synonyms += [u"Самсон"]
    Brand.findOrCreate(u"Птицефабрика Калужская").synonyms += [u"Рококо"]
    Brand.findOrCreate(u"ЕВРОДОН").synonyms += [u"ГВУ Индолина"]
    Brand.findOrCreate(u"ПРОДУКТЫ ОТ ИЛЬИНОЙ").synonyms += [u"От Ильиной"]
    Brand.findOrCreate(u"Колпинский, Ильина").synonyms += [u"От Ильиной"]
    Brand.findOrCreate(u"Айс Продукт").synonyms += [u"От Ильиной"]
    Brand.findOrCreate(u"Рыбообрабатывающий комбинат №1").synonyms += [u"Аморе", u"РОК1", u"РОК-1"]
    Brand.findOrCreate(u"РОК-1").synonyms += Brand.findOrCreate(u"Рыбообрабатывающий комбинат №1").synonyms
    Brand.findOrCreate(u"а'море").synonyms += Brand.findOrCreate(u"Рыбообрабатывающий комбинат №1").synonyms
    Brand.findOrCreate(u'БРПИ').synonyms += [u"Баскин Роббинс", u"Baskin Robbins"]
    Brand.findOrCreate(u'Baskin Robbins').synonyms += Brand.findOrCreate(u'БРПИ').synonyms
    Brand.findOrCreate(u'Балтийский берег').synonyms += [u"Балтийский Берег", u"По-царски", u"ББ", u"Балт Берег"]
    Brand.findOrCreate(u'Орими трейд').synonyms += [u"Jardin", u'Жардин', u"Орими", u"Супремо", u"Суматра Мандхелинг", u"Десерт Кап", u'Стиль ди Милано', u'Клауд Форест']
    Brand.findOrCreate(u'Jardin').synonyms += Brand.findOrCreate(u'Орими трейд').synonyms


    return (prodcsvname, toprint, catcsvname, brandscsvname)

# prefix can be consumed by re parser and must be returned in sub - must be always 1st Match
RE_TEMPLATE_PFQN_PRE = u'(?:\s|\.|,|\()'
# post is predicate and isn't consumed by parser. but must start immediately after term group
RE_TEMPLATE_PFQN_POST = u'(?=\s|$|,|\.|\)|/)'

RE_TEMPLATE_PFQN_WEIGHT_FULL = u'(\D)(' +\
                u'(?:\d+(?:шт|пак)?\s*(?:х|\*|x|/))?\s*' +\
                u'(?:\d+(?:[\.,]\d+)?\s*)' +\
                u'(?:кг|г|л|мл|гр)\.?' +\
                u'(?:(?:х|\*|x|/)\d+(?:\s*шт)?)?' +\
                u')' + RE_TEMPLATE_PFQN_POST
RE_TEMPLATE_PFQN_WEIGHT_SHORT = u'(\D' + RE_TEMPLATE_PFQN_PRE + u')((?:кг|г|л|мл|гр)\.?)' + RE_TEMPLATE_PFQN_POST
__pfqn_re_weight_full = re.compile(RE_TEMPLATE_PFQN_WEIGHT_FULL)
__pfqn_re_weight_short = re.compile(RE_TEMPLATE_PFQN_WEIGHT_SHORT)

RE_TEMPLATE_PFQN_FAT_MDZH = u'(?:\s*(?:с\s)?м\.?д\.?ж\.? в сух(?:ом)?\.?\s?вещ(?:-|ест)ве\s*' + \
                            u'|\s*массовая доля жира в сухом веществе\s*)?'
RE_TEMPLATE_PFQN_FAT = u'(' + RE_TEMPLATE_PFQN_PRE + u')(' + RE_TEMPLATE_PFQN_FAT_MDZH + \
                       u'(?:\d+(?:[\.,]\d+)?%?-)?\d+(?:[\.,]\d+)?\s*%(?:\s*жирн(?:\.|ости)?)?' + \
                       RE_TEMPLATE_PFQN_FAT_MDZH + u")" + RE_TEMPLATE_PFQN_POST
__pfqn_re_fat = re.compile(RE_TEMPLATE_PFQN_FAT)

RE_TEMPLATE_PFQN_PACK = u'(' + RE_TEMPLATE_PFQN_PRE + u')' \
                        u'(т/пак|ж/б|ст/б|м/у|с/б|ст\\\б|ст/бут|пл/б|пл/бут|пэтбутылка|пл|кор\.?' + \
                        u'|\d*\s*пак\.?|\d+\s*таб|\d+\s*саше|\d+\s*пир(?:\.|амидок)?' + \
                        u'|(?:\d+\s*)?шт\.?|упак\.?|уп\.?|в/у|п/э|жесть|' \
                        u'вакуум|нарезка|нар|стакан|ванночка|в\sванночке|дой-пак|дой/пак|пюр-пак|пюр\sпак|' + \
                        u'зип|зип-пакет|д/пак|п/пак|пл\.упаковка|пэт|пакет|туба|ведро|бан|лоток|фольга' + \
                        u'|фас(?:ованные)?|н/подл\.?|ф/пакет|0[.,]5|0[.,]75|0[.,]33)' + RE_TEMPLATE_PFQN_POST
__pfqn_re_pack = re.compile(RE_TEMPLATE_PFQN_PACK)

def parse_pfqn(pfqn):
    """
    Parse Full Product Name and return name parts: weight, fat, pack and SQN
    SQN is shorten product type name without above attributes and with normilized spaces and non word symbols
    If some attributes have multiple values - return concatenated string with " + " delimiter
    (see @cleanup_token_str)
    @param unicode pfqn: Full Product Name
    @rtype: (unicode, unicode, unicode, unicode)
    """
    sqn = pfqn.lower()

    def _add_match(ll, match):
        _pre = match.group(1)
        _m = match.group(2)
        ll[0] = (ll[0] + u" + " if ll[0] else "") + _m.strip()
        return _pre

    # weight - if has digit should be bounded by non-Digit, if has no digit - than unit only is acceptable but as token
    wl = [u""]
    sqn = re.sub(__pfqn_re_weight_full, lambda g: _add_match(wl, g), sqn)
    if not wl[0]:
        sqn = re.sub(__pfqn_re_weight_short, lambda g: _add_match(wl, g), sqn )
    # fat
    fl=[u""]
    sqn = re.sub(__pfqn_re_fat, lambda g: _add_match(fl, g), sqn )
    # pack
    pl=[u""]
    sqn = re.sub(__pfqn_re_pack, lambda g: _add_match(pl, g), sqn )

    return wl[0], fl[0], pl[0], cleanup_token_str(sqn)


if __name__ == '__main__':
    (prodcsvname, toprint, catcsvname, brandscsvname) = configure()

    cats = Cats()
    if catcsvname is not None:
        cats.load(catcsvname)
        print "Categories've been loaded from '%s': %d" % (catcsvname, len(cats))
    ignore_category_id_list = [cats.find_by_title(u"Алкогольные напитки"), cats.find_by_title(u"Скидки")]

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

            if ignore_category_id_list and any(cats.is_product_under(item["id"], cat_id) for cat_id in ignore_category_id_list if cat_id):
                continue

            product_manufacturer = None
            if item.get("details"):
                details = json.loads(item["details"])
                """ @type details: dict of (unicode, unicode) """

                brand = Brand.findOrCreate(details.get(ATTRIBUTE_BRAND, Brand.UNKNOWN_BRAND_NAME))

                product_manufacturer = details.get(ATTRIBUTE_MANUFACTURER)
                if product_manufacturer:
                    brand.manufacturers.add(product_manufacturer)
            else:
                brand = Brand.findOrCreate(Brand.UNKNOWN_BRAND_NAME)

            (weight, fat, pack, sqn) = parse_pfqn(pfqn)
            def __fill_fqn_dict(d, item):
                for k in item.split(u" + "): d[k] = d.get(k, 0) + 1
            __fill_fqn_dict(weights, weight)
            __fill_fqn_dict(fats, fat)
            __fill_fqn_dict(packs, pack)

            sqn_without_brand = sqn
            if brand.name != Brand.UNKNOWN_BRAND_NAME:
                sqn_without_brand = brand.replace_brand(sqn_without_brand)

            types[pfqn] = dict(weight=weight, fat=fat, pack=pack,
                               brand=brand.name,
                               sqn=sqn_without_brand,
                               brand_detected=sqn != sqn_without_brand,
                               product_manufacturer=product_manufacturer)

    # Process manufacturers as brands
    no_brand_manufacturers = {m for b_name in Brand.no_brand_names() for m in Brand.findOrCreate(b_name).manufacturers}

    for pfqn, item in types.iteritems():
        if not item["product_manufacturer"] and item["brand"] not in Brand.no_brand_names():
            # Cannot guess about manufacturer for real brand
            # TODO: Try to link the same manufacturer names with different spelling by brand name
            continue

        product_manufacturer = item["product_manufacturer"]
        brand = Brand.exist(item["brand"])
        sqn = item["sqn"]

        sqn_without_brand = sqn
        linked_manufacturers = {product_manufacturer} if product_manufacturer else no_brand_manufacturers
        for manufacturer in linked_manufacturers:
            manufacturer_brand = Brand.findOrCreate_manufacturer_brand(manufacturer)
            if manufacturer_brand and manufacturer_brand != brand:
                # Consider manufacturer as brand - replace its synonyms
                sqn_without_brand = manufacturer_brand.replace_brand(sqn_without_brand)
                if sqn != sqn_without_brand:
                    item["sqn"] = sqn_without_brand
                    item["brand_detected"] = True

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
            for linked_m in [im for ib in b if Brand.exist(ib) for im in Brand.exist(ib).manufacturers
                             if im != m and ib not in Brand.no_brand_names() and (ib != u"О'КЕЙ" or m == u"ООО \"О'КЕЙ\"")]:
                print "    ==> %s [%s]" % (linked_m, "|".join(manufacturers[linked_m]))
        print "Total manufacturers: %d" % len(manufacturers)

    elif toprint == "producttypes":
        ptypes_count = 0
        nobrand_count = 0
        m_count = dict()
        # for t, d in sorted(types.iteritems(), key=lambda t: t[1]["sqn"].split(" ", 1)[0]):
        for t, d in sorted(types.iteritems(), key=lambda t: t[1]["product_manufacturer"]):
            if not d["brand_detected"] and (d["brand"] in Brand.no_brand_names()):
                # print '%s   => brand: %s, prod_man: %s, weight: %s, fat: %s, pack: %s, fqn: %s' % \
                #       (d["sqn"], d["brand"], d["product_manufacturer"], d["weight"], d["fat"], d["pack"], t)
                nobrand_count += 1

            elif not d["brand_detected"]:
                print '%s   => brand: %s, prod_man: %s, weight: %s, fat: %s, pack: %s, fqn: %s' % \
                     (d["sqn"], d["brand"], d["product_manufacturer"], d["weight"], d["fat"], d["pack"], t)
                m_count[d["brand"]] = m_count.get(d["brand"], 0)
                m_count[d["brand"]] += 1
                ptypes_count += 1
        print
        print "Total product types: %d [notintype: %d, nobrand: %d]" % (len(types), ptypes_count, nobrand_count)
        print
        for m, c in sorted(m_count.iteritems(), key=lambda t:t[1], reverse=True):
            print "%d : %s" % (c, m)

    elif toprint == "typetuples":
        types2 = dict()
        for t, d in sorted(types.iteritems(), key=lambda t: t[1]["sqn"].split(" ", 1)[0]):
            words = re.split(u'\s+', d["sqn"])
            first_word = words.pop(0)
            if not words:
                words.append(u'')
            buf = ''
            for w in words:
                if w or len(words) == 1:
                    if w in [u'в', u'с', u'со', u'из', u'для', u'и', u'на', u'без', u'к', u'не']:
                        buf = w  # join proposition to the next word
                        continue
                    w = buf + u' ' + w if buf else w
                    types2[(first_word, w)] = types2.get((first_word, w), 0) + 1
                    buf = u''

        num_tuples = dict()
        # for t, c in sorted(types2.iteritems(), key=lambda k: types2[k[0]], reverse=True):
        for t, c in sorted(types2.iteritems(), key=lambda k: k[0][0]):
            if c <= 1: continue
            print "Tuple %s + %s: %d" % (t[0], t[1], c)
            num_tuples[c] = num_tuples.get(c, 0) + 1
        print "Total tuples: %d" % sum(num_tuples.values())
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

    if brandscsvname:
        with open(brandscsvname, 'wb') as f:
            f.truncate()
            Brand.to_csv(f)
        print "Stored %d brands to csv[%s]" % (len(Brand.all()), brandscsvname)


