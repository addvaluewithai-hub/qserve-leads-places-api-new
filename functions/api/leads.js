function json(data, status = 200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function onRequestGet({ env }) {
  if (!env.DB) return json({ error: 'D1 binding DB is missing in Cloudflare Pages.' }, 500);
  try {
    const result = await env.DB.prepare(`
      SELECT id,name,price_level,rating,user_rating_count,business_status,phone,website,
             google_maps_url,address,latitude,longitude,primary_type,types,opening_hours,
             source_label,source_query,source_type,source_area,status,priority,notes,
             first_source_batch,latest_source_batch,first_seen_at,last_seen_at,crm_updated_at
      FROM leads
      ORDER BY CASE price_level
        WHEN 'PRICE_LEVEL_VERY_EXPENSIVE' THEN 3
        WHEN 'PRICE_LEVEL_EXPENSIVE' THEN 2
        WHEN 'PRICE_LEVEL_MODERATE' THEN 1 ELSE 0 END DESC,
        rating DESC,
        user_rating_count DESC
    `).all();
    return json({ leads: result.results || [] });
  } catch (error) {
    return json({ error: error.message || 'Failed to load leads from D1.' }, 500);
  }
}
