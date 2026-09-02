function json(data, status = 200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function onRequestGet({ env }) {
  if (!env.DB) return json({ error: 'D1 binding DB is missing in Cloudflare Pages.' }, 500);
  try {
    const result = await env.DB.prepare(`
      SELECT c.id,c.name,c.vertical,c.description,c.active,c.created_at,c.updated_at,
             COUNT(cl.lead_id) AS lead_count,
             SUM(CASE WHEN cl.qualified = 1 THEN 1 ELSE 0 END) AS qualified_count,
             MAX(cl.last_seen_at) AS last_lead_seen_at
      FROM campaigns c
      LEFT JOIN campaign_leads cl ON cl.campaign_id = c.id
      WHERE c.active = 1
      GROUP BY c.id,c.name,c.vertical,c.description,c.active,c.created_at,c.updated_at
      ORDER BY c.name
    `).all();
    return json({ campaigns: result.results || [] });
  } catch (error) {
    return json({ error: error.message || 'Failed to load campaigns from D1.' }, 500);
  }
}
