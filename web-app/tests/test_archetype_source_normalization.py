"""Regression tests for tournament records consumed by the archetype explorer."""

from services.tournament_normalization import (normalized_tournaments,
    verified_seed_events, eligible_seed_entry)


def event(folder, *, stars=3, date='2026-07-01'):
    return {'folder': folder, 'name': folder, 'rating': stars, 'event_date': date}


def deck(deck_id, *, kind='Constructed'):
    return {'id': deck_id, 'format': kind, 'spellbook': [{'name': 'Firebolt'}]}


def normalize(events, sources):
    return normalized_tournaments(events, lambda folder: sources[folder])[0]


def test_top8_list_order_is_finishing_order():
    folder = 'New Grand Contest 2026'
    rows = [deck('first'), deck('second'), deck('third')]
    full = rows + [deck('field')]
    tournaments = normalize([event(folder)], {folder: {'top8': rows, 'all': full}})
    assert len(tournaments) == 1
    ranks = {r['deck']['id']: (r['placement'], r['top8']) for r in tournaments[0]['records']}
    assert ranks == {'first': (1, True), 'second': (2, True), 'third': (3, True), 'field': (None, False)}


def test_sorcerycon_sources_merge_and_use_top8_order():
    top = 'Sorcery Con Constructed 2026'
    everyone = 'Every one at Sorcery Con Constructed 2026'
    tournaments = normalize([event(top), event(everyone)], {
        top: {'top8': [deck('champion'), deck('runner-up')], 'all': []},
        everyone: {'top8': [], 'all': [deck('runner-up'), deck('other')]},
    })
    assert len(tournaments) == 1
    ranks = {r['deck']['id']: r['placement'] for r in tournaments[0]['records']}
    assert ranks == {'champion': 1, 'runner-up': 2, 'other': None}
    assert tournaments[0]['sourceFolders'] == [top, everyone]


def test_sorceryfest_counts_as_three_star_with_top8_order():
    folder = 'SorceryFest July 4th 2026'
    rows = [deck(f'd{i}') for i in range(8)]
    tournaments = normalize([event(folder, stars=1)], {folder: {'top8': rows, 'all': rows}})
    assert len(tournaments) == 1
    values = [(r['placement'], r['top8']) for r in tournaments[0]['records']]
    assert values == [(i, True) for i in range(1, 9)]


def test_gothic_one_finalists_are_top_cut_not_verified_top8():
    folder = 'Summit Gothic Season 1 2026'
    rows = [deck('other'), deck('cmlbrpok600j604lat67an03o')]
    tournaments = normalize([event(folder)], {folder: {'top8': [], 'all': rows}})
    result = {r['deck']['id']: r for r in tournaments[0]['records']}
    assert result['other']['topCut'] is True and result['other']['top8'] is False
    assert result['cmlbrpok600j604lat67an03o']['placement'] == 1


def test_gothic_three_repeated_decks_count_once_in_list_order():
    folder = 'Summit Gothic Season 3 2026'
    ids = ['a', 'b', 'c', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i']
    tournaments = normalize([event(folder, stars=1)], {folder: {'top8': [deck(k) for k in ids], 'all': []}})
    ranks = {r['deck']['id']: r['placement'] for r in tournaments[0]['records']}
    assert ranks == {'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 6, 'g': 7, 'h': 8, 'i': None}
    assert all(r['topCut'] for r in tournaments[0]['records'])


def test_constructed_only_and_eligible_three_star():
    events = [event('Allowed Grand Contest 2026'), event('Limited Grand Contest 2026'),
              event('Two Star Grand Contest 2026', stars=2), event('Old Grand Contest 2025', date='2025-05-01')]
    sources = {e['folder']: {'all': [deck(e['folder'])], 'top8': []} for e in events}
    sources['Allowed Grand Contest 2026']['all'] += [deck('draft', kind='Draft'), deck('sealed', kind='Sealed'), deck('unknown', kind='')]
    tournaments = normalize(events, sources)
    assert len(tournaments) == 1
    assert [r['deck']['id'] for r in tournaments[0]['records']] == ['Allowed Grand Contest 2026']


def test_verified_event_format_can_supply_missing_deck_format():
    folder = 'Verified Grand Contest 2026'
    tournament = event(folder)
    tournament['format'] = 'Constructed'
    rows = [deck('unknown', kind=''), deck('draft', kind='Draft')]
    tournaments = normalize([tournament], {folder: {'all': rows, 'top8': []}})
    assert [r['deck']['id'] for r in tournaments[0]['records']] == ['unknown']


def test_seed_registry_only_allows_curated_2026_constructed_tournaments():
    registry = verified_seed_events()
    assert len(registry) == 11
    assert eligible_seed_entry({'event': 'Gothic Season 4', 'date': '2026-07-18'}, known_events=registry)
    assert not eligible_seed_entry({'event': 'Some random event', 'date': '2026-07-18'}, known_events=registry)
    assert not eligible_seed_entry({'event': 'SCG CON Dallas', 'date': '2025-09-05'}, known_events=registry)
    assert not eligible_seed_entry({'event': 'SCG CON Dallas'}, known_events=registry)


def test_explicit_seed_draft_and_sealed_are_rejected_even_in_curated_events():
    registry = verified_seed_events()
    entry = {'event': 'SCG CON Dallas', 'date': '2026-09-05'}
    assert eligible_seed_entry(entry, known_events=registry, deck_format=None)
    assert eligible_seed_entry(entry, known_events=registry, deck_format='Constructed')
    assert not eligible_seed_entry(entry, known_events=registry, deck_format='Draft')
    assert not eligible_seed_entry(entry, known_events=registry, deck_format='Sealed')
