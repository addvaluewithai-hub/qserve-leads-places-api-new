#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

GOOGLE_API_KEY = os.environ['GOOGLE_API_KEY']
ACCOUNT_ID = os.environ['CLOUDFLARE_ACCOUNT_ID']
API_TOKEN = os.environ['CLOUDFLARE_API_TOKEN']
DATABASE_ID = os.environ['D1_DATABASE_ID']

D1_URL = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DATABASE_ID}/query'
PLACES_BASE = 'https://places.googleapis.com/v1'
OUT = Path(os.environ.get('OUT_DIR', 'out')) / 'google-photo-enrichment'
OUT.mkdir(parents=True, exist_ok=True)

DETAIL_MASK = ','.join([
    'id',
    'displayName',
    'formattedAddress',
    'priceLevel',
    'rating',
    'userRatingCount',
    'nationalPhoneNumber',
    'internationalPhoneNumber',
    'websiteUri',
    'googleMapsUri',
    'businessStatus',
    'location',
    'primaryType',
    'types',
    'regularOpeningHours',
    'photos',
])


def d1_query(sql: str, params=None):
    body = {'sql': sql}
    if params is not None:
        body['params'] = params
    req = urllib.request.Request(
        D1_URL,
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
    result = payload.get('result') or []
    if not result:
        return []
    if result[0].get('success') is False:
        raise RuntimeError(result[0])
    return result[0].get('results') or []


def google_json(url: str, field_mask: str | None = None):
    headers = {'X-Goog-Api-Key': GOOGLE_API_KEY}
    if field_mask:
        headers['X-Goog-FieldMask'] = field_mask
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode())


def safe_slug(value: str):
    value = re.sub(r'[^a-zA-Z0-9]+', '-', value).strip('-').lower()
    return value[:60] or 'venue'


def extension_for(content_type: str):
    content_type = (content_type or '').split(';')[0].strip().lower()
    return {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/webp': '.webp',
    }.get(content_type, '.jpg')


def download_photo(photo_name: str, target_stem: Path):
    quoted_name = urllib.parse.quote(photo_name, safe='/')
    query = urllib.parse.urlencode({
        'maxWidthPx': 1400,
        'maxHeightPx': 1400,
        'key': GOOGLE_API_KEY,
    })
    url = f'{PLACES_BASE}/{quoted_name}/media?{query}'
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=90) as response:
        content_type = response.headers.get('Content-Type', '')
        data = response.read()
    ext = extension_for(content_type)
    target = target_stem.with_suffix(ext)
    target.write_bytes(data)
    return target, content_type, len(data)


def main():
    # Mirror the CRM lead-score idea so "first two cafes" means our strongest
    # true cafe/coffee-shop leads, not arbitrary insertion order or restaurants
    # that merely include cafe in their secondary Google types.
    rows = d1_query('''
      SELECT id, name, primary_type, price_level, rating, user_rating_count, phone,
             website, google_maps_url
      FROM leads
      WHERE lower(COALESCE(primary_type, '')) IN ('cafe', 'coffee_shop')
      ORDER BY (
        COALESCE(rating, 0) * 20
        + MIN(COALESCE(user_rating_count, 0), 3000) / 40.0
        + CASE price_level
            WHEN 'PRICE_LEVEL_VERY_EXPENSIVE' THEN 30
            WHEN 'PRICE_LEVEL_EXPENSIVE' THEN 18
            WHEN 'PRICE_LEVEL_MODERATE' THEN 6
            ELSE 0
          END
        + CASE WHEN phone IS NOT NULL AND trim(phone) <> '' THEN 8 ELSE 0 END
      ) DESC,
      user_rating_count DESC
      LIMIT 2
    ''')

    if len(rows) < 2:
        raise SystemExit(f'Expected at least 2 cafe leads in D1, found {len(rows)}')

    summary = []
    for index, row in enumerate(rows, 1):
        place_id = row['id']
        details_url = f'{PLACES_BASE}/places/{urllib.parse.quote(place_id, safe="")}'
        details = google_json(details_url, DETAIL_MASK)
        name = details.get('displayName', {}).get('text') or row.get('name') or place_id
        venue_dir = OUT / f'{index:02d}-{safe_slug(name)}'
        venue_dir.mkdir(parents=True, exist_ok=True)

        photos = details.get('photos') or []
        print(f'[{index}/2] {name}')
        print(f'  Place ID: {place_id}')
        print(f'  Type: {details.get("primaryType") or row.get("primary_type")}')
        print(f'  Rating: {details.get("rating")} ({details.get("userRatingCount", 0)} reviews)')
        print(f'  Website: {details.get("websiteUri") or "none"}')
        print(f'  Google photos returned: {len(photos)}')

        downloaded = []
        errors = []
        for photo_index, photo in enumerate(photos[:8], 1):
            photo_name = photo.get('name')
            if not photo_name:
                continue
            try:
                target, content_type, size = download_photo(
                    photo_name,
                    venue_dir / f'google-photo-{photo_index:02d}',
                )
                downloaded.append({
                    'file': str(target.relative_to(OUT)),
                    'photo_name': photo_name,
                    'width_px': photo.get('widthPx'),
                    'height_px': photo.get('heightPx'),
                    'author_attributions': photo.get('authorAttributions') or [],
                    'content_type': content_type,
                    'bytes': size,
                })
                print(f'  downloaded photo {photo_index}: {target.name} ({size} bytes)')
            except Exception as exc:
                errors.append({'photo_name': photo_name, 'error': str(exc)})
                print(f'  photo {photo_index} download failed: {exc}')

        record = {
            'selected_from_d1': row,
            'google_place_details': details,
            'downloaded_photos': downloaded,
            'photo_download_errors': errors,
        }
        (venue_dir / 'enrichment.json').write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        summary.append({
            'rank': index,
            'id': place_id,
            'name': name,
            'primary_type': details.get('primaryType') or row.get('primary_type'),
            'rating': details.get('rating'),
            'reviews': details.get('userRatingCount'),
            'price_level': details.get('priceLevel'),
            'website': details.get('websiteUri'),
            'maps': details.get('googleMapsUri'),
            'photos_available': len(photos),
            'photos_downloaded': len(downloaded),
            'directory': venue_dir.name,
        })

    (OUT / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print('\nExperiment summary:')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
