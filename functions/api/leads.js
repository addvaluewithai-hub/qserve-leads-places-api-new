function json(data, status = 200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function onRequestGet({ env, request }) {
  if (!env.DB) return json({ error: 'D1 binding DB is missing in Cloudflare Pages.' }, 500);
  const url = new URL(request.url);
  const campaignId = url.searchParams.get('campaign');
  const qualifiedOnly = url.searchParams.get('qualified') !== '0';

  try {
    if (campaignId) {
      const result = await env.DB.prepare(`
        SELECT
          l.id,l.name,l.price_level,l.rating,l.user_rating_count,l.business_status,l.phone,l.website,
          l.google_maps_url,l.address,l.latitude,l.longitude,l.primary_type,l.types,l.opening_hours,
          cl.campaign_id,cl.qualified,cl.quality_score,cl.qualification_reason,cl.source_area,cl.source_query,
          cl.source_term,cl.status,cl.priority,cl.notes,cl.first_seen_at,cl.last_seen_at,cl.crm_updated_at,
          s.latest_sampled_review_at,s.latest_sampled_review_age_days,s.sampled_review_count,
          s.recent_sampled_reviews,s.sampled_review_avg,s.review_signal_checked_at,s.review_signal_note
        FROM campaign_leads cl
        JOIN leads l ON l.id = cl.lead_id
        LEFT JOIN lead_signals s ON s.campaign_id = cl.campaign_id AND s.lead_id = cl.lead_id
        WHERE cl.campaign_id = ? AND (? = 0 OR cl.qualified = 1)
        ORDER BY cl.quality_score DESC, l.rating DESC, l.user_rating_count DESC
      `).bind(campaignId, qualifiedOnly ? 1 : 0).all();
      return json({ campaignId, qualifiedOnly, leads: result.results || [] });
    }

    const result = await env.DB.prepare(`
      SELECT id,name,price_level,rating,user_rating_count,business_status,phone,website,
             google_maps_url,address,latitude,longitude,primary_type,types,opening_hours,
             source_label,source_query,source_type,source_area,status,priority,notes,
             first_source_batch,latest_source_batch,first_seen_at,last_seen_at,crm_updated_at
      FROM leads
      ORDER BY rating DESC, user_rating_count DESC
    `).all();
    return json({ campaignId: null, qualifiedOnly: false, leads: result.results || [] });
  } catch (error) {
    return json({ error: error.message || 'Failed to load leads from D1.' }, 500);
  }
}
