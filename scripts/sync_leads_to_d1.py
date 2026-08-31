#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

ACCOUNT_ID = os.environ['CLOUDFLARE_ACCOUNT_ID']
API_TOKEN = os.environ['CLOUDFLARE_API_TOKEN']
DATABASE_ID = os.environ['D1_DATABASE_ID']
API_URL = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query'

ROOT = Path(__file__).resolve().parents[1]
OLD_FILE = ROOT / 'public' / 'noncheap_october_leads.json'
NEW_FILE = ROOT / 'out' / 'noncheap_october_leads.json'
SCHEMA_FILE = ROOT / 'schema.sql'


def query(sql: str, params=None):
    body = {'sql': sql}
    if params is not None:
        body['params'] = params
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        method='POST',
        headers={
            'Authorization': f'Bearer {API_TOKEN}',
            'Content-Type': 'application/json',
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read().decode())
    if not payload.get('success'):
        raise RuntimeError(payload)
    results = payload.get('result') or []
    for result in results:
        if result.get('success') is False:
            raise RuntimeError(result)
    return results


def load(path: Path):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    return data if isinstance(data, list) else []


def main():
    # Apply schema statements one by one so indexes/tables are idempotent.
    schema = SCHEMA_FILE.read_text(encoding='utf-8')
    for statement in [part.strip() for part in schema.split(';') if part.strip()]:
        query(statement)

    old = load(OLD_FILE)
    new = load(NEW_FILE)
    merged = {}
    for batch_name, rows in [('legacy-json', old), ('google-refresh', new)]:
        for row in rows:
            place_id = row.get('id')
            if not place_id:
                continue
            row = dict(row)
            row['_batch'] = batch_name
            merged[place_id] = row

    sql = '''
    INSERT INTO leads (
      id,name,price_level,rating,user_rating_count,business_status,phone,website,
      google_maps_url,address,latitude,longitude,primary_type,types,opening_hours,
      source_label,source_query,source_type,source_area,first_source_batch,latest_source_batch
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET
      name=excluded.name,
      price_level=excluded.price_level,
      rating=excluded.rating,
      user_rating_count=excluded.user_rating_count,
      business_status=excluded.business_status,
      phone=excluded.phone,
      website=excluded.website,
      google_maps_url=excluded.google_maps_url,
      address=excluded.address,
      latitude=excluded.latitude,
      longitude=excluded.longitude,
      primary_type=excluded.primary_type,
      types=excluded.types,
      opening_hours=excluded.opening_hours,
      source_label=excluded.source_label,
      source_query=excluded.source_query,
      source_type=excluded.source_type,
      source_area=excluded.source_area,
      latest_source_batch=excluded.latest_source_batch,
      last_seen_at=CURRENT_TIMESTAMP
    '''

    for i, row in enumerate(merged.values(), 1):
        params = [
            row.get('id'), row.get('name') or 'Unnamed venue',
            row.get('price_level') or 'PRICE_LEVEL_UNSPECIFIED', row.get('rating'),
            row.get('user_rating_count') or 0, row.get('business_status'), row.get('phone'),
            row.get('website'), row.get('google_maps_url'), row.get('address'),
            row.get('latitude'), row.get('longitude'), row.get('primary_type'), row.get('types'),
            row.get('opening_hours'), row.get('source_label'), row.get('source_query'),
            row.get('source_type'), row.get('source_area'), row['_batch'], row['_batch'],
        ]
        query(sql, params)
        if i % 25 == 0:
            print(f'Upserted {i}/{len(merged)} leads')

    result = query('SELECT COUNT(*) AS total FROM leads')
    total = result[0].get('results', [{}])[0].get('total') if result else None
    breakdown = query('SELECT price_level, COUNT(*) AS count FROM leads GROUP BY price_level ORDER BY count DESC')
    print(f'Old JSON rows: {len(old)}')
    print(f'Fresh Google rows: {len(new)}')
    print(f'Unique rows submitted: {len(merged)}')
    print(f'D1 total leads: {total}')
    print('Price breakdown:', json.dumps(breakdown[0].get('results', []) if breakdown else []))


if __name__ == '__main__':
    main()
