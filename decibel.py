# Paradise.SPL: фід Decibel для Prom.ua (тільки stdlib).
# Id оферів лишаються як у постачальника (без префікса). Ціни, валюта і наявність не змінюються.
# Категорії порталу: decibel_categories.csv. Теги офера за документацією Prom
# (support.prom.ua, «Імпорт через YML»): <portal_category_id>, <portal_category_url>.
# Якщо вказані обидва, portal_category_id має пріоритет.
import csv
import os
import re
import sys
import xml.etree.ElementTree as ET
import urllib.request

URL = 'https://api.decibel.com.ua/feed/drop_uk.xml'
MIN_OFFERS = 250
ROOT = os.path.dirname(os.path.abspath(__file__))
# Бренды, которых нет в прайсе Decibel. Оферы с таким <vendor> не попадают в фид.
# Сравнение без учёта регистра и крайних пробелов — список удобно править.
EXCLUDED_VENDORS = {'KiurLab', 'SWAG', 'Deaf Bonce', 'AVATAR'}
MAP_PATH = os.path.join(ROOT, 'decibel_categories.csv')
# Довші назви раніше, щоб «JL Audio» не розпався на коротший токен.
BRANDS = (
    'Deaf Bonce', 'JL Audio', 'Bass Habit', 'KiurLab', 'UAudio',
    'AVATAR', 'SWAG', 'DLS', 'GAS', 'NFL',
)
PART_TAGS = ('vendorCode', 'article', 'sku', 'code')
PART_PARAMS = {
    'артикул', 'артикул виробника', 'код запчастини', 'код виробника',
    'article', 'sku', 'vendorcode',
}
BRAND_PARAMS = {'бренд', 'виробник', 'brand', 'vendor'}


def load_rules(path):
    rules = []
    with open(path, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            cid = (row.get('decibel_category_id') or '').strip()
            if not cid:
                continue
            pattern = (row.get('name_regex') or '').strip()
            rules.append({
                'category_id': cid,
                'regex': re.compile(pattern, re.I) if pattern else None,
                'portal_category_id': (row.get('portal_category_id') or '').strip(),
                'portal_category_url': (row.get('portal_category_url') or '').strip(),
                'status': (row.get('status') or '').strip(),
                'name': (row.get('decibel_category_name') or '').strip(),
                'portal_name': (row.get('portal_category_name') or '').strip(),
            })
    if not rules:
        sys.exit(f'empty mapping: {path}')
    return rules


def match_rule(rules, category_id, name):
    fallback = None
    for rule in rules:
        if rule['category_id'] != category_id:
            continue
        if rule['regex'] is None:
            if fallback is None:
                fallback = rule
            continue
        if rule['regex'].search(name or ''):
            return rule
    return fallback


def text_of(el):
    return (el.text or '').strip() if el is not None else ''


def insert_after(parent, anchor_tag, element):
    anchor = parent.find(anchor_tag)
    if anchor is None:
        parent.append(element)
        return
    parent.insert(list(parent).index(anchor) + 1, element)


def upsert_text(parent, tag, value, after_tag):
    el = parent.find(tag)
    if el is None:
        el = ET.Element(tag)
        insert_after(parent, after_tag, el)
    el.text = value


def upsert_param(offer, name, value):
    """Додає характеристику. Вже заповнене значення не переписує."""
    if not value:
        return False
    for param in offer.findall('param'):
        if (param.get('name') or '').strip() == name:
            if text_of(param):
                return False
            param.text = value
            return True
    el = ET.Element('param', {'name': name})
    el.text = value
    insert_after(offer, 'vendor', el)
    return True


def derive_vendor(offer):
    vendor = text_of(offer.find('vendor'))
    if vendor:
        return vendor
    for param in offer.findall('param'):
        if (param.get('name') or '').strip().lower() in BRAND_PARAMS and text_of(param):
            return text_of(param)
    blob = ' '.join(filter(None, [
        offer.findtext('name'),
        offer.findtext('name_ru'),
        offer.findtext('model'),
    ]))
    for brand in BRANDS:
        if re.search(r'(?<!\w)' + re.escape(brand) + r'(?!\w)', blob, re.I):
            return brand
    return ''


def part_code(offer):
    """Артикул, якщо він уже є у фіді (тег або характеристика)."""
    for tag in PART_TAGS:
        value = text_of(offer.find(tag))
        if value:
            return value
    for param in offer.findall('param'):
        if (param.get('name') or '').strip().lower() in PART_PARAMS and text_of(param):
            return text_of(param)
    return ''


QTY_RE = re.compile(r'\(\s*\d+\s*шт\.?\s*\)', re.I)


def name_tail(offer, vendor):
    """Частина назви після бренду, без «(2 шт.)»."""
    name = text_of(offer.find('name'))
    m = re.search(r'(?<!\w)' + re.escape(vendor) + r'(?!\w)', name, re.I) if vendor else None
    tail = name[m.end():] if m else ''
    return ' '.join(QTY_RE.sub(' ', tail).split())


def model_code(offer, vendor):
    """Модель з назви: перший токен з цифрою після бренду (MNA-70.4, PM2-84, FHA11).
    Якщо токен починається з цифри або короткий (80A, H4, S8, RC3) — разом із
    попереднім словом (MAF 80A, AF 250, Shine H4). Без цифр — увесь хвіст назви
    (E-Tape, Test Bag). Порожньо — id офера."""
    tokens = name_tail(offer, vendor).split()
    for i, tok in enumerate(tokens):
        if re.search(r'\d', tok):
            if i > 0 and (tok[0].isdigit() or len(tok) <= 3):
                return f'{tokens[i - 1]} {tok}'
            return tok
    return ' '.join(tokens) or (offer.get('id') or '')


def commercial(offer):
    return (
        offer.get('id'),
        offer.get('available'),
        offer.findtext('price'),
        offer.findtext('currencyId'),
        offer.findtext('stock_quantity'),
    )


def is_excluded(offer):
    vendor = text_of(offer.find('vendor')).lower()
    return vendor in {name.strip().lower() for name in EXCLUDED_VENDORS}


def drop_empty_categories(shop, offers):
    """Удаляет <category>, на которые не ссылается ни один оставшийся офер. Родителей сохраняет."""
    cats = shop.find('categories')
    if cats is None:
        return
    parent = {c.get('id'): c.get('parentId') for c in cats}
    need = {text_of(o.find('categoryId')) for o in offers}
    need.discard('')
    for cid in list(need):
        while parent.get(cid):
            cid = parent[cid]
            need.add(cid)
    for cat in list(cats):
        if cat.get('id') not in need:
            cats.remove(cat)


def main():
    rules = load_rules(MAP_PATH)
    try:
        req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
        raw = urllib.request.urlopen(req, timeout=120).read()
        root = ET.fromstring(raw)
    except Exception as exc:
        sys.exit(f'download/parse failed: {exc}')
    shop = root.find('shop')
    offers_el = shop.find('offers') if shop is not None else None
    if offers_el is None:
        sys.exit('no offers element')
    source_offers = list(offers_el)
    src_all_ids = [o.get('id') for o in source_offers]
    if any(not i for i in src_all_ids) or len(src_all_ids) != len(set(src_all_ids)):
        sys.exit('source offer ids are missing or not unique')
    # Сначала отсекаем бренды вне прайса: проверка категории портала их не касается.
    excluded = [o for o in source_offers if is_excluded(o)]
    for offer in excluded:
        offers_el.remove(offer)
    offers = list(offers_el)
    if len(offers) < MIN_OFFERS:
        sys.exit(f'too few offers: {len(offers)}')
    # Оставшиеся id — это id источника без исключённых брендов, без префикса.
    src_ids = [o.get('id') for o in offers]
    kept_source_ids = [o.get('id') for o in source_offers if not is_excluded(o)]
    if src_ids != kept_source_ids:
        sys.exit('kept offer ids differ from source minus excluded vendors')
    before = [commercial(o) for o in offers]

    needs_check = 0
    vendor_filled = 0
    vendor_added = 0
    part_filled = 0
    code_derived = 0
    codes = {}
    derived = []
    for offer in offers:
        cid = text_of(offer.find('categoryId'))
        rule = match_rule(rules, cid, offer.findtext('name') or '')
        if rule is None or not rule['portal_category_id'] or not rule['portal_category_url']:
            sys.exit(f'no portal category for offer {offer.get("id")} category {cid}')
        upsert_text(offer, 'portal_category_id', rule['portal_category_id'], 'categoryId')
        upsert_text(offer, 'portal_category_url', rule['portal_category_url'], 'portal_category_id')
        if rule['status'] == 'needs check':
            needs_check += 1
        vendor = derive_vendor(offer)
        if vendor:
            if not text_of(offer.find('vendor')):
                vendor_added += 1
                el = offer.find('vendor')
                if el is None:
                    el = ET.Element('vendor')
                    insert_after(offer, 'name', el)
                el.text = vendor
            if upsert_param(offer, 'Виробник', vendor):
                vendor_filled += 1
        code = part_code(offer)
        if not code:
            # У джерелі немає артикула: беремо модель з назви (fallback — id офера).
            code = model_code(offer, vendor)
            code_derived += 1
            derived.append(offer)
        codes[offer.get('id')] = (vendor, code)

    # Короткий код не унікальний у бренду (V1 White/Red, MAD/MAX PM2-64, NFL C10W 31/36 mm)
    # — для таких беремо всю назву після бренду.
    seen = {}
    for vendor, code in codes.values():
        seen[(vendor.lower(), code.lower())] = seen.get((vendor.lower(), code.lower()), 0) + 1
    for offer in derived:
        vendor, code = codes[offer.get('id')]
        if seen[(vendor.lower(), code.lower())] > 1:
            codes[offer.get('id')] = (vendor, name_tail(offer, vendor) or code)
    for offer in offers:
        code = codes[offer.get('id')][1]
        if upsert_param(offer, 'Код запчастини', code):
            part_filled += 1
        if not text_of(offer.find('vendorCode')):
            upsert_text(offer, 'vendorCode', code, 'vendor')

    drop_empty_categories(shop, offers)

    after = [commercial(o) for o in offers]
    out_ids = [o.get('id') for o in offers]
    if out_ids != src_ids:
        sys.exit('offer id set changed')
    if after != before:
        sys.exit('price, currency, availability or stock changed')
    if len(offers) != len(src_ids):
        sys.exit('offer count changed')
    missing_portal = [
        o.get('id') for o in offers
        if not text_of(o.find('portal_category_id')) or not text_of(o.find('portal_category_url'))
    ]
    if missing_portal:
        sys.exit(f'offers without portal category: {len(missing_portal)}')
    def has_param(o, name):
        return any((p.get('name') or '').strip() == name and text_of(p) for p in o.findall('param'))
    missing_params = [
        o.get('id') for o in offers
        if not has_param(o, 'Виробник') or not has_param(o, 'Код запчастини')
    ]
    if missing_params:
        sys.exit(f'offers without Виробник/Код запчастини: {missing_params[:20]}')

    os.makedirs(os.path.join(ROOT, 'public'), exist_ok=True)
    ET.indent(root, space='  ')
    out_path = os.path.join(ROOT, 'public', 'decibel_prom.xml')
    ET.ElementTree(root).write(out_path, encoding='UTF-8', xml_declaration=True)
    csv_path = os.path.join(ROOT, 'public', 'decibel_excluded.csv')
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh, delimiter=';')
        writer.writerow(['id', 'vendor', 'name'])
        for offer in excluded:
            writer.writerow([
                offer.get('id') or '',
                text_of(offer.find('vendor')),
                text_of(offer.find('name')),
            ])

    # Повторная проверка записанного файла: id и цены = источник без исключённых брендов.
    saved = ET.parse(out_path).getroot()
    saved_offers = list(saved.find('shop').find('offers'))
    if [o.get('id') for o in saved_offers] != src_ids:
        sys.exit('written offer ids differ from source')
    if [commercial(o) for o in saved_offers] != before:
        sys.exit('written commercial fields differ from source')
    banned = {name.strip().lower() for name in EXCLUDED_VENDORS}
    if any(text_of(o.find('vendor')).lower() in banned for o in saved_offers):
        sys.exit('written feed still contains an excluded vendor')
    with open(csv_path, 'rb') as fh:
        if not fh.read(3) == b'\xef\xbb\xbf':
            sys.exit('excluded csv has no utf-8 bom')
    with open(csv_path, encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.reader(fh, delimiter=';'))
    if rows[:1] != [['id', 'vendor', 'name']] or [r[0] for r in rows[1:]] != [o.get('id') for o in excluded]:
        sys.exit('excluded csv does not match dropped offers')

    index = os.path.join(ROOT, 'public', 'index.html')
    with open(index, 'w', encoding='utf-8') as fh:
        fh.write(
            '<!DOCTYPE html>\n'
            '<meta charset="utf-8">\n'
            '<title>Paradise.SPL feeds</title>\n'
            '<ul>\n'
            '<li><a href="cyclone_prom.xml">cyclone_prom.xml</a> — Cyclone</li>\n'
            '<li><a href="decibel_prom.xml">decibel_prom.xml</a> — Decibel</li>\n'
            '<li><a href="decibel_excluded.csv">decibel_excluded.csv</a> — снятые оферы Decibel</li>\n'
            '</ul>\n'
        )
    print(
        f'offers: {len(offers)} '
        f'excluded: {len(excluded)} '
        f'portal: {len(offers)} '
        f'needs_check: {needs_check} '
        f'vendor_param: {vendor_filled} '
        f'vendor_tag_added: {vendor_added} '
        f'part_code_param: {part_filled} '
        f'part_code_from_name: {code_derived}'
    )


if __name__ == '__main__':
    main()
