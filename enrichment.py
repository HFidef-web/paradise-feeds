# Постійний шар характеристик і категорій Prom.ua.
# Scheduled rebuild завантажує фіди постачальників наново. Цей модуль щоразу
# накладає data/enrichment_overlay.json, тож додані <param> і виправлені
# portal_category_id не зникають. Ціни, наявність, валюта, кількість, фото,
# id оферів і склад оферів не змінюються. Категорія, чия офіційна назва
# закінчується на «загальне», відхиляється.
import csv
import json
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
OVERLAY_PATH = os.path.join(ROOT, 'data', 'enrichment_overlay.json')
CATEGORIES_PATH = os.path.join(ROOT, 'reference', 'prom_portal_categories.csv')
# Групи Cyclone, для яких офіційний leaf Prom збігається з categoryId фіда.
# Для інших груп portal_category_id з categoryId не виводиться.
CYCLONE_GROUP_PORTAL = frozenset({
    '340415',    # Автомагнітоли
    '12123208',  # Альтернативна оптика
    '12020613',  # Led- лампи автомобільні
    '12020603',  # Додаткові, протитуманні фари
})
SKIPPED_TAGS = frozenset({'param', 'portal_category_id', 'portal_category_url'})


def _exit(message):
    sys.exit(f'enrichment: {message}')


def load_categories():
    cats = {}
    with open(CATEGORIES_PATH, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            cid = (row.get('id') or '').strip()
            name = (row.get('name') or '').strip()
            url = (row.get('url') or '').strip()
            if not cid or not name or not url:
                _exit(f'official category row is incomplete: {cid or name}')
            if cid in cats:
                _exit(f'duplicate official category id {cid}')
            cats[cid] = {'name': name, 'url': url}
    banned = [c for c in cats.values() if c['name'].casefold().endswith('загальне')]
    if len(cats) < 5000 or len(banned) < 100:
        _exit('official Prom category table is incomplete')
    return cats


def load_overlay(feed):
    with open(OVERLAY_PATH, encoding='utf-8') as fh:
        data = json.load(fh)
    feeds = data.get('feeds') if isinstance(data, dict) else None
    if not isinstance(feeds, dict) or feed not in feeds or not isinstance(feeds[feed], dict):
        _exit(f'overlay has no {feed} feed')
    return feeds[feed]


def require_portal(cats, portal_id):
    rec = cats.get(portal_id)
    if rec is None:
        _exit(f'portal category {portal_id} is not in the official Prom export')
    if rec['name'].casefold().endswith('загальне'):
        _exit(f'refusing Prom category {portal_id} «{rec["name"]}»')
    return rec


def protected_signature(offer):
    attrs = tuple(sorted(offer.attrib.items()))
    children = []
    for el in list(offer):
        if el.tag in SKIPPED_TAGS:
            continue
        kids = tuple((c.tag, c.text, tuple(sorted(c.attrib.items()))) for c in list(el))
        children.append((el.tag, el.text, tuple(sorted(el.attrib.items())), kids))
    return attrs, tuple(children)


def param_signature(offer):
    return [
        ((p.get('name') or '').strip(), (p.get('unit') or '').strip(), (p.text or '').strip())
        for p in offer.findall('param')
    ]


def set_child(parent, tag, value):
    found = parent.findall(tag)
    if len(found) > 1:
        _exit(f'offer {parent.get("id")} has several <{tag}>')
    if found:
        found[0].text = value
        return
    el = ET.Element(tag)
    el.text = value
    parent.append(el)


def _positive(name, value, unit, oid):
    if not unit:
        return
    try:
        number = float(value.replace(',', '.'))
    except ValueError:
        _exit(f'offer {oid} param {name}={value!r} is not numeric')
    if number <= 0:
        _exit(f'offer {oid} param {name}={value!r} is not positive')


def apply_params(offer, params):
    oid = offer.get('id')
    if not isinstance(params, list):
        _exit(f'offer {oid} params are not a list')
    existing = {
        (p.get('name') or '').strip(): ((p.text or '').strip(), (p.get('unit') or '').strip())
        for p in offer.findall('param')
    }
    seen = set()
    added = 0
    for raw in params:
        if not isinstance(raw, dict):
            _exit(f'offer {oid} has a malformed param')
        name = str(raw.get('name') or '').strip()
        value = str(raw.get('value') or '').strip()
        unit = str(raw.get('unit') or '').strip()
        if not name or not value:
            _exit(f'offer {oid} has an empty param')
        if name in seen:
            _exit(f'offer {oid} overlay repeats param {name}')
        seen.add(name)
        _positive(name, value, unit, oid)
        current = existing.get(name)
        if current is not None:
            if current != (value, unit):
                _exit(f'offer {oid} param {name} conflicts with overlay ({current[0]!r} vs {value!r})')
            continue
        attrib = {'name': name}
        if unit:
            attrib['unit'] = unit
        el = ET.Element('param', attrib)
        el.text = value
        offer.append(el)
        added += 1
    return added


def _watts(offer, name):
    for param in offer.findall('param'):
        if (param.get('name') or '').strip() != name:
            continue
        if (param.get('unit') or '').strip() != 'Вт':
            continue
        return float((param.text or '').replace(',', '.'))
    return None


def apply_feed(root, feed):
    """Накласти overlay на вже зібраний фід. Повертає лічильники."""
    if feed not in ('decibel', 'cyclone'):
        _exit(f'unknown feed {feed}')
    cats = load_categories()
    for portal_id in CYCLONE_GROUP_PORTAL:
        require_portal(cats, portal_id)
    overlay = load_overlay(feed)
    shop = root.find('shop')
    offers_el = shop.find('offers') if shop is not None else None
    if offers_el is None:
        _exit('no offers element')
    offers = list(offers_el)
    before_ids = [o.get('id') for o in offers]
    before_sig = [protected_signature(o) for o in offers]
    before_params = [param_signature(o) for o in offers]

    params_added = 0
    portal_ids = 0
    for offer in offers:
        oid = offer.get('id') or ''
        rec = overlay.get(oid) or {}
        if rec and not isinstance(rec, dict):
            _exit(f'offer {oid} overlay entry is not an object')
        portal_id = str(rec.get('portal_category_id') or '').strip()
        old_portal = str(rec.get('old_portal_category_id') or '').strip()
        if portal_id:
            current = (offer.findtext('portal_category_id') or '').strip()
            if old_portal and current and current not in {old_portal, portal_id}:
                _exit(
                    f'offer {oid}: portal_category_id {current} is neither '
                    f'{old_portal} nor {portal_id}'
                )
        elif feed == 'cyclone':
            group = (offer.findtext('categoryId') or '').strip()
            if group in CYCLONE_GROUP_PORTAL and not (offer.findtext('portal_category_id') or '').strip():
                portal_id = group
        if portal_id:
            info = require_portal(cats, portal_id)
            set_child(offer, 'portal_category_id', portal_id)
            portal_ids += 1
            if feed == 'decibel':
                set_child(offer, 'portal_category_url', info['url'])
        params_added += apply_params(offer, rec.get('params') or [])

    after = list(offers_el)
    if [o.get('id') for o in after] != before_ids:
        _exit('offer ids or order changed')
    if len(after) != len(offers):
        _exit('offer count changed')
    if [protected_signature(o) for o in after] != before_sig:
        _exit('a price, photo, quantity or other protected field changed')
    for old, offer in zip(before_params, after):
        if param_signature(offer)[:len(old)] != old:
            _exit(f'offer {offer.get("id")} rewrote an existing param')
        nominal = _watts(offer, 'Номінальна потужність')
        maximum = _watts(offer, 'Максимальна потужність')
        if nominal is not None and maximum is not None and nominal > maximum:
            _exit(f'offer {offer.get("id")} nominal power {nominal} exceeds max {maximum}')
        names = [(p.get('name') or '').strip() for p in offer.findall('param')]
        if any(not name or not (p.text or '').strip() for name, p in zip(names, offer.findall('param'))):
            _exit(f'offer {offer.get("id")} has an empty param')
        if len(names) != len(set(names)):
            _exit(f'offer {offer.get("id")} has duplicate params')
        portal_id = (offer.findtext('portal_category_id') or '').strip()
        if portal_id:
            require_portal(cats, portal_id)
        elif feed == 'decibel':
            _exit(f'offer {offer.get("id")} has no portal category')

    for offer in after:
        rec = overlay.get(offer.get('id') or '')
        if not rec:
            continue
        have = set(param_signature(offer))
        for raw in rec.get('params') or []:
            key = (
                str(raw.get('name') or '').strip(),
                str(raw.get('unit') or '').strip(),
                str(raw.get('value') or '').strip(),
            )
            if key not in have:
                _exit(f'offer {offer.get("id")} lost overlay param {key[0]}')
        wanted = str(rec.get('portal_category_id') or '').strip()
        if wanted and (offer.findtext('portal_category_id') or '').strip() != wanted:
            _exit(f'offer {offer.get("id")} lost portal category {wanted}')

    return {'params_added': params_added, 'portal_ids': portal_ids, 'offers': len(after)}
