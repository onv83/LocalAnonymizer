"""Offline geography contract; fixtures contain public place names only."""
import importlib.util
import pytest
import hashlib
from importlib.resources import files


def test_offline_provenance_and_every_stored_form(monkeypatch):
    import socket
    import local_anonymizer.russian_geography as geo
    def forbidden(*args, **kwargs):
        raise AssertionError('geography must not access the network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    geo._resource.cache_clear()
    geo.load_locations.cache_clear()
    geo._trie.cache_clear()
    root = files('local_anonymizer').joinpath('assets/russian_geography')
    assert hashlib.sha256(root.joinpath('hflabs-city.csv').read_bytes()).hexdigest() == geo.resource_manifest()['source_sha256']
    assert 'Creative Commons' in root.joinpath('CC-BY-SA-4.0.txt').read_text(encoding='utf-8')
    assert 'creativecommons.org/licenses/by-sa/4.0/' in root.joinpath('HFLABS-README.md').read_text(encoding='utf-8')
    for row in geo.load_locations():
        for form in row.forms:
            matches = list(geo.find_locations(form, location_context=True))
            assert len(matches) == 1, (row.id, form)
            assert matches[0].surface == form
            assert row.id in matches[0].location_ids


def test_rebuild_is_byte_deterministic():
    import runpy
    from pathlib import Path
    builder = Path(__file__).resolve().parents[1] / 'scripts/build_russian_geography.py'
    root = files('local_anonymizer').joinpath('assets/russian_geography/locations.json')
    before = root.read_bytes()
    runpy.run_path(str(builder), run_name='__main__')
    assert root.read_bytes() == before


def test_matcher_precise_spans_and_canonical_identity():
    import local_anonymizer.russian_geography as geo
    assert hasattr(geo, 'find_locations')
    text = 'Из Нижнего Новгорода в Нижнем\u00a0Новгороде; Ростове-на-Дону, г. Орел.'
    matches = list(geo.find_locations(text))
    assert [text[m.start:m.end] for m in matches] == [
        'Нижнего Новгорода', 'Нижнем\u00a0Новгороде', 'Ростове-на-Дону', 'Орел']
    assert matches[0].location_ids == matches[1].location_ids
    assert matches[0].canonical_names == ('Нижний Новгород',)
    assert all(m.surface == text[m.start:m.end] for m in matches)


@pytest.mark.parametrize('text', [
    'мирный договор', 'Свободный порт', 'Видное место', 'клин материала', 'орёл на гербе',
    'Бор сосен', 'первого мая', 'Советский район', 'Владимир сообщил',
    'Томский модуль и пермский модуль', 'Рабочая область и Предметная область',
    'Центральный Уральский', 'id_Москва2', 'Москваabc', 'Москва́',
    'Нижний\ufdd0Новгород', 'Нижний\tНовгород', 'Нижний\ufdd3Новгород',
])
def test_no_ordinary_word_or_identifier_overmatch(text):
    from local_anonymizer.russian_geography import find_locations
    assert list(find_locations(text)) == []


def test_ambiguous_forms_need_local_context_not_global_learning():
    from local_anonymizer.russian_geography import find_locations
    text = 'в городе Мирном, Мирный договор; г. Бор; Владимир'
    assert [m.surface for m in find_locations(text)] == ['Мирном', 'Бор']
    assert [m.surface for m in find_locations('Владимир', location_context=True)] == ['Владимир']


def test_longest_regions_unicode_and_case():
    from local_anonymizer.russian_geography import find_locations
    text = 'В Ханты-Мансийском автономном округе — Югре, МОСКОВСКОЙ ОБЛАСТИ; г. ОРЁЛ, г. Орел.'
    matches = list(find_locations(text))
    assert [m.surface for m in matches] == [
        'Ханты-Мансийском автономном округе — Югре', 'МОСКОВСКОЙ ОБЛАСТИ', 'ОРЁЛ', 'Орел']
    assert matches[-1].location_ids == matches[-2].location_ids


@pytest.mark.parametrize('canonical, forms', [
    ('Республика Татарстан', ['Татарстан', 'Татарстана', 'Татарстану', 'Татарстаном', 'Татарстане']),
    ('Республика Башкортостан', ['Башкортостане', 'Башкортостаном']),
    ('Республика Коми', ['Коми']),
    ('Республика Марий Эл', ['Марий Эл']),
])
def test_bare_republic_names_share_official_identity(canonical, forms):
    from local_anonymizer.russian_geography import find_locations
    official = next(find_locations(canonical))
    for form in forms:
        matches = list(find_locations(form))
        assert len(matches) == 1, form
        assert matches[0].location_ids == official.location_ids
        assert matches[0].surface == form


def test_plural_and_irregular_city_cases():
    from local_anonymizer.russian_geography import find_locations
    for form, canonical in [('Мытищах', 'Мытищи'), ('Ельце', 'Елец'),
                            ('Старом Осколе', 'Старый Оскол'), ('Вышнем Волочке', 'Вышний Волочек')]:
        matches = list(find_locations(form, location_context=True))
        assert len(matches) == 1, form
        assert canonical in matches[0].canonical_names
        assert matches[0].surface == form


def test_offline_resource_inventory():
    assert importlib.util.find_spec('local_anonymizer.russian_geography') is not None
    from local_anonymizer.russian_geography import load_locations, resource_manifest
    rows = load_locations()
    manifest = resource_manifest()
    assert len([r for r in rows if r.kind == 'city']) == 1117
    assert len([r for r in rows if r.kind == 'region']) == 85
    assert len({r.id for r in rows}) == len(rows)
    assert manifest['license'] == 'CC-BY-SA-4.0'
    assert manifest['source_date'] == '2021-10-11'
    assert manifest['source_commit'] == 'ae661bffe572880472249097c9b29c42b09650ea'
    assert all(r.canonical in r.forms for r in rows)


def test_finite_forms_and_source_city_fallback():
    from local_anonymizer.russian_geography import load_locations
    cities = {r.canonical: r for r in load_locations() if r.kind == 'city'}
    expected = {
        'Дмитров': 'Дмитрове', 'Москва': 'Москвой', 'Нижний Новгород': 'Нижнем Новгороде',
        'Ростов-на-Дону': 'Ростове-на-Дону', 'Камень-на-Оби': 'Камня-на-Оби',
        'Гусь-Хрустальный': 'Гусём-Хрустальным', 'Санкт-Петербург': 'Санкт-Петербурге',
        'Великие Луки': 'Великих Луках', 'Набережные Челны': 'Набережных Челнах',
    }
    for canonical, form in expected.items():
        assert canonical in cities, canonical
        assert form in cities[canonical].forms, (canonical, form)
    regions = {r.canonical: r for r in load_locations() if r.kind == 'region'}
    for canonical, form in {
        'Московская область': 'Московской области',
        'Республика Татарстан': 'Республике Татарстан',
        'Краснодарский край': 'Краснодарском крае',
        'Республика Саха (Якутия)': 'Республике Саха (Якутия)',
        'Ханты-Мансийский автономный округ — Югра': 'Ханты-Мансийском автономном округе — Югре',
    }.items():
        assert canonical in regions, canonical
        assert form in regions[canonical].forms, (canonical, form)
