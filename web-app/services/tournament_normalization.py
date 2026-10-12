"""Turn raw Summit event folders into one record per actual Gothic-era tournament.

Historical exceptions are data, not code: edit tournament_exceptions.json to add
aliases, verified ranking policies, or a confirmed placement by Curiosa deck ID.

Placement policy: a Top 8 list is in finishing order, so its first eight
unique decks are places 1-8. Events without a Top 8 list only get the
placements curated in tournament_exceptions.json. Top Cut is not Top 8.
"""
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re

GOTHIC_START = '2025-12-05'
MIN_RATING = 3
EXCEPTIONS_PATH = Path(__file__).with_name('tournament_exceptions.json')


def load_exceptions(path=EXCEPTIONS_PATH):
    with Path(path).open(encoding='utf-8') as stream:
        data = json.load(stream)
    if data.get('schemaVersion') != 1:
        raise ValueError('Unsupported tournament exception file version')
    specs = data.get('tournaments') or {}
    alias_to_event = {}
    for event_id, spec in specs.items():
        for alias in spec.get('folders', []):
            key = _normalize_folder(alias)
            if key in alias_to_event:
                raise ValueError(f'Conflicting aliases for {alias}')
            alias_to_event[key] = event_id
    return specs, alias_to_event


def verified_seed_events(path=EXCEPTIONS_PATH):
    """Names approved as Gothic-era, 3-star Constructed in the curated snapshot.

    These seed entries have no folder-level star rating. Do not silently accept
    a newly added or rebranded seed event without reviewing its eligibility.
    """
    with Path(path).open(encoding='utf-8') as stream:
        data = json.load(stream)
    if data.get('schemaVersion') != 1:
        raise ValueError('Unsupported tournament exception file version')
    return frozenset(data.get('verifiedSeedEvents') or ())


def eligible_seed_entry(entry, *, known_events, deck_format=None):
    """Only retain a vetted seed tournament result, never a Draft/Sealed deck.

    An absent deck format is acceptable ONLY for these explicitly reviewed
    Constructed seed tournaments. Exact formats other than Constructed are vetoed.
    """
    if not isinstance(entry, dict) or entry.get('event') not in known_events:
        return False
    raw_date = entry.get('date') or ''
    try:
        if date.fromisoformat(str(raw_date)[:10]) < date.fromisoformat(GOTHIC_START):
            return False
    except ValueError:
        return False
    kind = str(deck_format or '').strip().lower()
    return kind in ('', 'constructed')


def _normalize_folder(value):
    return re.sub(r'[^a-z0-9]+', ' ', (value or '').lower()).strip()


def _in_gothic_era(event, spec):
    raw = str(event.get('event_date') or '').strip()
    if raw:
        try:
            return date.fromisoformat(raw[:10]) >= date.fromisoformat(GOTHIC_START)
        except ValueError:
            return False
    # A date in the approved exceptions has been reviewed manually.
    if spec.get('date'):
        return spec['date'] >= GOTHIC_START
    # No date available: only clearly labelled 2026 or Gothic records qualify.
    label = (str(event.get('folder') or '') + ' ' + str(event.get('name') or '')).lower()
    return ('gothic' in label or re.search(r'(?<!\d)2026(?!\d)', label) is not None)


def _allowed(event, spec):
    folder = str(event.get('folder') or '')
    if not folder or folder.startswith('_'):
        return False
    if re.search(r'\b(limited|draft|sealed)\b', folder + ' ' + str(event.get('name') or ''), re.I):
        return False
    return _in_gothic_era(event, spec)


def _is_constructed(record, *, verified_event_format=False):
    kind = str(record.get('format') or '').strip().lower()
    return kind == 'constructed' or (not kind and verified_event_format)


def normalized_tournaments(events, loader, *, exceptions_path=EXCEPTIONS_PATH):
    """Return (tournaments, diagnostics) without modifying source JSON files.

    A tournament has {id, name, date, records:[{deck, placement, top8,
    topCut, sourceFolder}], sourceFolders}. Unknown values are None, not False.
    This is deliberately independent of Flask and of the clustering algorithm.
    """
    specs, alias_map = load_exceptions(exceptions_path)
    grouped = defaultdict(list)
    for event in events:
        folder = str(event.get('folder') or '')
        key = alias_map.get(_normalize_folder(folder), folder)
        spec = specs.get(key, {})
        if _allowed(event, spec):
            grouped[key].append(event)

    report = {'sourceCollections': 0, 'mergedCollections': 0,
              'duplicateSourceRows': 0,
              'unusableRecords': 0, 'ignoredLowRatingGroups': 0,
              'correctedRatingGroups': 0, 'correctedRatingEvents': []}
    output = []
    for key, sources in sorted(grouped.items()):
        # Historical collections may have different ratings. If any one is
        # three-star, use every alias belonging to that same approved event.
        spec = specs.get(key, {})
        # Some historical event folders default to one star because they are
        # absent from EVENT_RATINGS. A manually reviewed three-star exception
        # restores those events without automatically promoting other events.
        rated_by_source = any(int(source.get('rating') or 0) == MIN_RATING for source in sources)
        rated_by_exception = spec.get('confirmedRating') == MIN_RATING
        if not rated_by_source and not rated_by_exception:
            report['ignoredLowRatingGroups'] += 1
            continue
        if rated_by_exception and not rated_by_source:
            report['correctedRatingGroups'] += 1
            report['correctedRatingEvents'].append(key)
        priority = { _normalize_folder(name): i for i, name in enumerate(spec.get('folders', [])) }
        sources.sort(key=lambda src: (priority.get(_normalize_folder(src['folder']), 999), src['folder']))
        report['sourceCollections'] += len(sources)
        report['mergedCollections'] += max(0, len(sources) - 1)
        verified_event_format = (str(spec.get('confirmedFormat') or '').lower() == 'constructed'
                                 or any(str(s.get('format') or '').lower() == 'constructed' for s in sources))
        by_id = {}
        top8_ids = set()
        topcut_ids = set()
        top8_order = []
        candidates_unusable = set()
        missing_id_rows = 0
        for src in sources:
            folder = src['folder']
            data = loader(folder) or {}
            listed_top8 = data.get('top8') or []
            # A Top 8-only event still has actual decklists to analyse.
            # Include both sources because the broad-field file may omit a finalist.
            raw = listed_top8 + (data.get('all') or [])
            if not isinstance(raw, list):
                continue
            is_top8_source = (not spec.get('top8Source') or
                              _normalize_folder(folder) == _normalize_folder(spec['top8Source']))
            if is_top8_source:
                for row in listed_top8:
                    if not isinstance(row, dict) or not row.get('id'):
                        continue
                    did = str(row['id'])
                    topcut_ids.add(did)
                    if did not in top8_ids and len(top8_order) < 8:
                        top8_order.append(did)
                        top8_ids.add(did)
            seen_here = set()
            for row in raw:
                if not isinstance(row, dict) or not row.get('id'):
                    missing_id_rows += 1
                    continue
                did = str(row['id'])
                if did in seen_here:
                    report['duplicateSourceRows'] += 1
                    continue
                seen_here.add(did)
                if not _is_constructed(row, verified_event_format=verified_event_format):
                    continue
                if did in by_id:
                    report['duplicateSourceRows'] += 1
                    continue
                by_id[did] = (row, folder)
        # The Top 8 list is kept in finishing order (the event admin can
        # reorder it), so its first unique decks are places 1-8. Curated
        # placements only fill in events that have no Top 8 list.
        ranked_top8 = bool(top8_order)
        if ranked_top8:
            placements = {did: position for position, did in enumerate(top8_order, 1)}
        else:
            placements = {str(did): int(pos) for did, pos in spec.get('placements', {}).items()}
        known_top8 = top8_ids
        records = []
        for did, (row, folder) in by_id.items():
            place = placements.get(did)
            in_top8 = (did in known_top8 or place is not None)
            in_top_cut = bool(spec.get('allTopCut') or did in topcut_ids or in_top8)
            records.append({'deck': row, 'sourceFolder': folder,
                            'placement': place, 'top8': in_top8, 'topCut': in_top_cut})
        if not records:
            continue
        report['unusableRecords'] += missing_id_rows
        output.append({
            'id': key,
            'name': spec.get('name') or sources[0].get('name') or sources[0]['folder'],
            'date': spec.get('date') or sources[0].get('event_date'),
            'sourceFolders': [source['folder'] for source in sources],
            'records': records,
            'placementPolicy': ('Top 8 list order' if ranked_top8 else
                                'curated placements only'),
        })
    return output, report
