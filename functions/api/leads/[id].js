const STATUSES = new Set(['New','Qualified','Contacted','Follow up','Won','Not fit']);
const PRIORITIES = new Set(['High','Medium','Low']);

function json(data, status = 200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function onRequestPatch({ env, params, request }) {
  if (!env.DB) return json({ error: 'D1 binding DB is missing in Cloudflare Pages.' }, 500);
  const id = String(params.id || '');
  if (!id) return json({ error: 'Lead id is required.' }, 400);

  let body;
  try { body = await request.json(); }
  catch { return json({ error: 'Invalid JSON body.' }, 400); }

  const updates = [];
  const values = [];
  if (body.status !== undefined) {
    if (!STATUSES.has(body.status)) return json({ error: 'Invalid status.' }, 400);
    updates.push('status = ?'); values.push(body.status);
  }
  if (body.priority !== undefined) {
    if (!PRIORITIES.has(body.priority)) return json({ error: 'Invalid priority.' }, 400);
    updates.push('priority = ?'); values.push(body.priority);
  }
  if (body.notes !== undefined) {
    updates.push('notes = ?'); values.push(String(body.notes).slice(0, 5000));
  }
  if (!updates.length) return json({ error: 'No CRM fields to update.' }, 400);

  updates.push('crm_updated_at = CURRENT_TIMESTAMP');
  const campaignId = body.campaignId ? String(body.campaignId) : null;

  if (campaignId) {
    values.push(campaignId, id);
    const result = await env.DB.prepare(
      `UPDATE campaign_leads SET ${updates.join(', ')} WHERE campaign_id = ? AND lead_id = ?`
    ).bind(...values).run();
    if (!result.meta?.changes) return json({ error: 'Campaign lead not found.' }, 404);
    const lead = await env.DB.prepare(
      'SELECT lead_id AS id,campaign_id,status,priority,notes,crm_updated_at FROM campaign_leads WHERE campaign_id = ? AND lead_id = ?'
    ).bind(campaignId, id).first();
    return json({ lead });
  }

  values.push(id);
  const result = await env.DB.prepare(`UPDATE leads SET ${updates.join(', ')} WHERE id = ?`).bind(...values).run();
  if (!result.meta?.changes) return json({ error: 'Lead not found.' }, 404);
  const lead = await env.DB.prepare('SELECT id,status,priority,notes,crm_updated_at FROM leads WHERE id = ?').bind(id).first();
  return json({ lead });
}
