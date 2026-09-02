const GOOGLE_ENDPOINT = 'https://places.googleapis.com/v1/places:searchText';
const ALLOWED_TYPES = new Set([
  'cafe', 'restaurant', 'lawyer', 'dentist', 'dental_clinic', 'doctor',
  'real_estate_agency', 'insurance_agency', 'accounting', 'plumber',
  'electrician', 'roofing_contractor', 'marketing_consultant',
]);
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
].join(',');

function json(data, status = 200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
}

function cleanNumber(value, fallback, min, max) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(Math.max(number, min), max);
}

export async function onRequestPost(context) {
  const apiKey = context.env.GOOGLE_API_KEY;
  if (!apiKey) return json({ error: 'GOOGLE_API_KEY is missing in Cloudflare Pages environment variables.' }, 500);

  let input;
  try { input = await context.request.json(); }
  catch { return json({ error: 'Invalid JSON request body.' }, 400); }

  const requestedType = String(input.type || '').trim();
  if (requestedType && !ALLOWED_TYPES.has(requestedType)) {
    return json({ error: `Unsupported place type: ${requestedType}` }, 400);
  }

  const includedType = requestedType || undefined;
  const priceLevels = Array.isArray(input.priceLevels)
    ? input.priceLevels.filter((level) => ALLOWED_PRICES.has(level))
    : [];
  const textQuery = String(input.query || includedType || 'business').slice(0, 200);
  const pageSize = Math.round(cleanNumber(input.pageSize, 20, 1, 20));

  const body = {
    textQuery,
    pageSize,
    strictTypeFiltering: input.strictTypeFiltering !== false,
  };
  if (includedType) body.includedType = includedType;
  if (priceLevels.length) body.priceLevels = priceLevels;
  if (input.pageToken) body.pageToken = String(input.pageToken).slice(0, 1000);
  if (input.regionCode) body.regionCode = String(input.regionCode).slice(0, 2).toUpperCase();
  if (input.languageCode) body.languageCode = String(input.languageCode).slice(0, 12);

  const hasCoordinates = input.lat !== undefined && input.lng !== undefined;
  if (hasCoordinates) {
    const lat = cleanNumber(input.lat, 0, -90, 90);
    const lng = cleanNumber(input.lng, 0, -180, 180);
    const radius = cleanNumber(input.radius, 5000, 100, 50000);
    body.locationBias = { circle: { center: { latitude: lat, longitude: lng }, radius } };
  }

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
  try { payload = text ? JSON.parse(text) : {}; }
  catch { payload = { raw: text }; }

  if (!response.ok) {
    return json({
      error: payload?.error?.message || 'Google Places request failed.',
      status: response.status,
      details: payload,
    }, response.status);
  }

  return json({ places: payload.places || [], nextPageToken: payload.nextPageToken || null });
}

export async function onRequestGet() {
  return json({
    ok: true,
    endpoint: 'POST /api/search',
    supportedTypes: [...ALLOWED_TYPES],
    note: 'Campaign automation should use scripts/run_campaign.py so filters, review signals and D1 provenance stay consistent.',
  });
}
