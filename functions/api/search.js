const GOOGLE_ENDPOINT = 'https://places.googleapis.com/v1/places:searchText';
const ALLOWED_TYPES = new Set(['cafe', 'restaurant']);
const ALLOWED_PRICES = new Set([
  'PRICE_LEVEL_INEXPENSIVE',
  'PRICE_LEVEL_MODERATE',
  'PRICE_LEVEL_EXPENSIVE',
  'PRICE_LEVEL_VERY_EXPENSIVE',
]);

const FIELD_MASK = [
  'places.id',
  'places.displayName',
  'places.formattedAddress',
  'places.priceLevel',
  'places.rating',
  'places.userRatingCount',
  'places.nationalPhoneNumber',
  'places.websiteUri',
  'places.googleMapsUri',
  'places.businessStatus',
  'places.location',
  'places.primaryType',
  'places.types',
  'places.regularOpeningHours',
  'places.photos',
].join(',');

function json(data, status = 200) {
  return Response.json(data, {
    status,
    headers: {
      'Cache-Control': 'no-store',
    },
  });
}

function cleanNumber(value, fallback, min, max) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(Math.max(number, min), max);
}

export async function onRequestPost(context) {
  const apiKey = context.env.GOOGLE_API_KEY;
  if (!apiKey) {
    return json({ error: 'GOOGLE_API_KEY is missing in Cloudflare Pages environment variables.' }, 500);
  }

  let input;
  try {
    input = await context.request.json();
  } catch {
    return json({ error: 'Invalid JSON request body.' }, 400);
  }

  const includedType = ALLOWED_TYPES.has(input.type) ? input.type : 'cafe';
  const priceLevels = Array.isArray(input.priceLevels)
    ? input.priceLevels.filter((level) => ALLOWED_PRICES.has(level))
    : [];

  const lat = cleanNumber(input.lat, 29.9724785, -90, 90);
  const lng = cleanNumber(input.lng, 30.9576332, -180, 180);
  const radius = cleanNumber(input.radius, 5000, 500, 50000);
  const textQuery = String(input.query || includedType).slice(0, 120);

  const body = {
    textQuery,
    includedType,
    strictTypeFiltering: true,
    pageSize: 20,
    locationBias: {
      circle: {
        center: { latitude: lat, longitude: lng },
        radius,
      },
    },
  };

  if (priceLevels.length) body.priceLevels = priceLevels;

  const response = await fetch(GOOGLE_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Goog-Api-Key': apiKey,
      'X-Goog-FieldMask': FIELD_MASK,
    },
    body: JSON.stringify(body),
  });

  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }

  if (!response.ok) {
    return json({
      error: payload?.error?.message || 'Google Places request failed.',
      status: response.status,
      details: payload,
    }, response.status);
  }

  return json({ places: payload.places || [] });
}

export async function onRequestGet() {
  return json({ ok: true, endpoint: 'POST /api/search', includes: ['photos', 'primaryType', 'types', 'openingHours'] });
}
