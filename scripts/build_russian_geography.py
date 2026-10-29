"""Rebuild the finite offline geography resource; stdlib only, never downloads.

Rules are applied only to names in the pinned CSV, at build time. They are not
an unrestricted runtime suffix recognizer. Unknown patterns stay nominative.
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src/local_anonymizer/assets/russian_geography'
# Six complete case forms: nominative, genitive, dative, accusative, instrumental, prepositional.
EXCEPTIONS = {
    'Мытищи': 'Мытищи|Мытищ|Мытищам|Мытищи|Мытищами|Мытищах',
    'Елец': 'Елец|Ельца|Ельцу|Елец|Ельцом|Ельце',
    'Камень': 'Камень|Камня|Камню|Камень|Камнем|Камне',
    'Орёл': 'Орёл|Орла|Орлу|Орёл|Орлом|Орле',
    'Орел': 'Орел|Орла|Орлу|Орел|Орлом|Орле',
    'Гусь': 'Гусь|Гуся|Гусю|Гусь|Гусём|Гусе',
    'Волочек': 'Волочек|Волочка|Волочку|Волочек|Волочком|Волочке',
    'Торжок': 'Торжок|Торжка|Торжку|Торжок|Торжком|Торжке',
    'Огни': 'Огни|Огней|Огням|Огни|Огнями|Огнях',
    'Поляны': 'Поляны|Полян|Полянам|Поляны|Полянами|Полянах',
    'Зори': 'Зори|Зорь|Зорям|Зори|Зорями|Зорях',
    'Луки': 'Луки|Лук|Лукам|Луки|Луками|Луках',
    'Серги': 'Серги|Серег|Сергам|Серги|Сергами|Сергах',
    'Воды': 'Воды|Вод|Водам|Воды|Водами|Водах',
    'Челны': 'Челны|Челнов|Челнам|Челны|Челнами|Челнах',
    'Клепики': 'Клепики|Клепиков|Клепикам|Клепики|Клепиками|Клепиках',
    'Поле': 'Поле|Поля|Полю|Поле|Полем|Поле',
    'Усолье': 'Усолье|Усолья|Усолью|Усолье|Усольем|Усолье',
    'край': 'край|края|краю|край|краем|крае',
    'область': 'область|области|области|область|областью|области',
    'Республика': 'Республика|Республики|Республике|Республику|Республикой|Республике',
    'Чувашия': 'Чувашия|Чувашии|Чувашии|Чувашию|Чувашией|Чувашии',
}
FEMININE_SOFT = {'Пермь', 'Тверь', 'Казань', 'Рязань', 'Астрахань', 'Тюмень', 'Керчь', 'Гавань', 'Обь'}
INDECLINABLE = {'Сочи', 'Улан-Удэ', 'Тарко-Сале', 'Лабытнанги', 'Саха', 'Коми', 'Марий Эл'}
AMBIGUOUS = {'Мирный', 'Свободный', 'Видное', 'Клин', 'Бор', 'Орёл', 'Орел', 'Майский',
             'Советский', 'Владимир', 'Александров', 'Пушкин', 'Королёв', 'Королев', 'Киров',
             'Жуков', 'Чехов', 'Лермонтов', 'Гагарин', 'Маркс', 'Шахты', 'Реж', 'Обь',
             'Дно', 'Удачный', 'Радужный', 'Родники', 'Грязи', 'Зима', 'Пласт'}


def cases(word):
    if word in EXCEPTIONS:
        return EXCEPTIONS[word].split('|')
    if word in INDECLINABLE:
        return [word] * 6
    stem = word[:-2]
    if word.endswith(('ский', 'цкий')):
        return [word, word[:-2]+'ого', word[:-2]+'ому', word, word[:-2]+'им', word[:-2]+'ом']
    if word.endswith(('ый', 'ой', 'ий')):
        soft = word.endswith('ний')
        endings = ['его', 'ему', 'им', 'ем'] if soft else ['ого', 'ому', 'ым', 'ом']
        if word.endswith(('кий', 'гий', 'хий')):
            endings[2] = 'им'
        return [word, stem+endings[0], stem+endings[1], word, stem+endings[2], stem+endings[3]]
    if word.endswith(('ая', 'яя')):
        soft = word.endswith('яя')
        return [word, stem+('ей' if soft else 'ой'), stem+('ей' if soft else 'ой'),
                stem+('юю' if soft else 'ую'), stem+('ей' if soft else 'ой'), stem+('ей' if soft else 'ой')]
    if word.endswith(('ые', 'ие')):
        s = 'и' if word.endswith('ие') else 'ы'
        return [word, stem+s+'х', stem+s+'м', word, stem+s+'ми', stem+s+'х']
    if word.endswith(('ое', 'ее')):
        soft = word.endswith('ее')
        return [word, stem+('его' if soft else 'ого'), stem+('ему' if soft else 'ому'), word,
                stem+('им' if soft else 'ым'), stem+('ем' if soft else 'ом')]
    if word in FEMININE_SOFT:
        return [word, word[:-1]+'и', word[:-1]+'и', word, word+'ю', word[:-1]+'и']
    if word.endswith('ия'):
        return [word, word[:-1]+'и', word[:-1]+'и', word[:-1]+'ю', word[:-1]+'ей', word[:-1]+'и']
    if word.endswith('а'):
        s = word[:-1]
        return [word, s+('и' if s[-1] in 'гкхжчшщ' else 'ы'), s+'е', s+'у', s+'ой', s+'е']
    if word.endswith('я'):
        return [word, word[:-1]+'и', word[:-1]+'е', word[:-1]+'ю', word[:-1]+'ей', word[:-1]+'е']
    if word.endswith(('ь', 'й')):
        s = word[:-1]
        return [word, s+'я', s+'ю', word, s+'ем', s+'е']
    if word[-1].lower() in 'бвгджзклмнпрстфхцчшщ':
        return [word, word+'а', word+'у', word, word+'ом', word+'е']
    # -ово/-ево/-ино/-ыно have optional declension; preserve both alternatives.
    if word.endswith(('ово', 'ево', 'ино', 'ыно')):
        return [word, word[:-1]+'а', word[:-1]+'у', word, word[:-1]+'ом', word[:-1]+'е']
    return [word] * 6


def city_cases(name):
    if name in INDECLINABLE:
        return [name] * 6
    if '-на-' in name:
        first, fixed = name.split('-на-', 1)
        return [v+'-на-'+fixed for v in cases(first)]
    if ' ' in name:
        parts = name.split(' ')
        return [' '.join(cases(p)[i] for p in parts) for i in range(6)]
    if '-' in name:
        first, last = name.rsplit('-', 1)
        # Geographic prefixes and possessive Гаврилов remain fixed; paired nouns
        # and adjective compounds decline both lexical components.
        both = first in {'Гусь', 'Юрьев', 'Петровск', 'Железногорск', 'Петропавловск',
            'Ленинск', 'Каменск', 'Спасск', 'Александровск', 'Переславль', 'Усолье'}
        left = cases(first) if both else [first]*6
        right = cases(last)
        return [left[i]+'-'+right[i] for i in range(6)]
    return cases(name)


def region_forms(kind, name):
    if kind == 'г':
        # Keep a distinct region ID without competing with bare city mentions.
        return ['город федерального значения '+x for x in city_cases(name)]
    if kind == 'Чувашия':
        return [' '.join((cases('Чувашская')[i], cases('Республика')[i])) for i in range(6)] + cases('Чувашия')
    if kind == 'обл' and name.startswith('Кемеровская'):
        basic = [cases('Кемеровская')[i]+' '+cases('область')[i] for i in range(6)]
        return [basic[i]+' — '+cases('Кузбасс')[i] for i in range(6)] + basic + cases('Кузбасс')
    if kind == 'АО':
        adjective = name.split(' ')[0]
        basic = [' '.join((cases(adjective)[i], cases('автономный')[i], cases('округ')[i])) for i in range(6)]
        if adjective == 'Ханты-Мансийский':
            return [basic[i]+' — '+cases('Югра')[i] for i in range(6)] + basic + cases('Югра')
        return basic
    if kind in {'обл', 'Аобл', 'край'}:
        noun = 'край' if kind == 'край' else 'область'
        return [cases(name)[i]+(' автономная' if kind == 'Аобл' and i == 0 else
            ' автономную' if kind == 'Аобл' and i == 3 else ' автономной' if kind == 'Аобл' else '')+
            ' '+cases(noun)[i] for i in range(6)]
    if name == 'Саха /Якутия/':
        return [cases('Республика')[i]+' Саха (Якутия)' for i in range(6)] + ['Саха (Якутия)'] + cases('Якутия')
    if name == 'Северная Осетия - Алания':
        return [cases('Республика')[i]+' '+cases('Северная')[i]+' '+cases('Осетия')[i]+' — '+cases('Алания')[i] for i in range(6)]
    if name.endswith(('ая', 'яя')):
        return [cases(name)[i]+' '+cases('Республика')[i] for i in range(6)]
    # Republic names are appositions: "в Республике Татарстан", not "Татарстане".
    # Bare nominal republic names decline independently of the official title.
    # Do not strip adjective republic titles (handled above): that would turn
    # ordinary adjectives into geography matches.
    return [r+' '+name for r in cases('Республика')] + city_cases(name)


def build():
    raw = (ROOT / 'hflabs-city.csv').read_bytes()
    rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    locations = []
    for row in rows:
        name = row['city'] or row['settlement'] or (row['area'] if row['area_type'] == 'г' else row['region'])
        forms = sorted(set([name] + city_cases(name)))
        ambiguous = name in AMBIGUOUS or (' ' not in name and '-' not in name and name.endswith(('ый', 'ий', 'ой', 'ое', 'ая')))
        locations.append(dict(id='city:' + row['fias_id'], kind='city', canonical=name,
                              forms=forms, requires_context=ambiguous))
    for kind, name in sorted({(r['region_type'], r['region']) for r in rows}):
        identity = hashlib.sha256((kind + ':' + name).encode()).hexdigest()[:16]
        forms = region_forms(kind, name)
        locations.append(dict(id='region:' + identity, kind='region', canonical=forms[0],
                              forms=sorted(set(forms)), requires_context=False))
    manifest = dict(schema_version=1, license='CC-BY-SA-4.0', source_date='2021-10-11',
                    source_commit='ae661bffe572880472249097c9b29c42b09650ea',
                    source_url='https://github.com/hflabs/city',
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                    city_count=len(rows), region_count=len(locations)-len(rows),
                    modifications='Finite build-time case forms, curated compounds, region titles, context guards; no external morphology data.',
                    scope='HFLabs 2021-10-11 snapshot, not a current or exhaustive administrative register; includes Crimea per upstream naming without asserting sovereignty.')
    (ROOT / 'locations.json').write_text(json.dumps(dict(manifest=manifest, locations=locations),
        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    build()
