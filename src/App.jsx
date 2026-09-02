import { useEffect, useMemo, useState } from 'react';
import { Download, ExternalLink, Filter, Globe2, Phone, RefreshCw, Search, Star } from 'lucide-react';

const STATUS_OPTIONS = ['New', 'Qualified', 'Contacted', 'Follow up', 'Won', 'Not fit'];
const PRIORITY_OPTIONS = ['High', 'Medium', 'Low'];
const DEFAULT_FILTERS = {
  text: '', status: 'All', priority: 'All', minRating: '0', minReviews: '0',
  hasPhone: false, hasWebsite: false, sort: 'score', qualifiedOnly: true,
};

function fallbackScore(lead) {
  const rating = Number(lead.rating || 0);
  const reviews = Number(lead.user_rating_count || 0);
  return Math.round(Math.min(100, rating * 14 + Math.log10(reviews + 1) * 10 + (lead.website ? 8 : 0) + (lead.phone ? 6 : 0)));
}

function scoreOf(lead) {
  return Number.isFinite(Number(lead.quality_score)) ? Number(lead.quality_score) : fallbackScore(lead);
}

function compareLeads(a, b, sort) {
  if (sort === 'rating') return Number(b.rating || 0) - Number(a.rating || 0);
  if (sort === 'reviews') return Number(b.user_rating_count || 0) - Number(a.user_rating_count || 0);
  if (sort === 'freshness') return Number(a.latest_sampled_review_age_days ?? 999999) - Number(b.latest_sampled_review_age_days ?? 999999);
  if (sort === 'name') return String(a.name).localeCompare(String(b.name));
  return scoreOf(b) - scoreOf(a);
}

function csvEscape(value) { return `"${String(value ?? '').replaceAll('"', '""')}"`; }

function freshnessLabel(lead) {
  const age = lead.latest_sampled_review_age_days;
  if (age === null || age === undefined) return 'Unknown';
  if (Number(age) === 0) return 'Today';
  return `${age}d ago`;
}

export function App() {
  const [campaigns, setCampaigns] = useState([]);
  const [campaignId, setCampaignId] = useState('');
  const [leads, setLeads] = useState([]);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [savingIds, setSavingIds] = useState(new Set());

  useEffect(() => { loadCampaigns(); }, []);
  useEffect(() => { loadLeads(); }, [campaignId, filters.qualifiedOnly]);

  async function loadCampaigns() {
    try {
      const response = await fetch('/api/campaigns', { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Could not load campaigns.');
      const rows = payload.campaigns || [];
      setCampaigns(rows);
      if (!campaignId && rows.length) setCampaignId(rows[0].id);
    } catch (err) {
      setError(`Campaign list: ${err.message}`);
    }
  }

  async function loadLeads() {
    setLoading(true); setError('');
    try {
      const params = new URLSearchParams();
      if (campaignId) params.set('campaign', campaignId);
      if (campaignId) params.set('qualified', filters.qualifiedOnly ? '1' : '0');
      const response = await fetch(`/api/leads${params.toString() ? `?${params}` : ''}`, { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Could not load CRM leads from D1.');
      setLeads(payload.leads || []);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  async function updateCrm(id, patch) {
    const before = leads;
    const body = campaignId ? { ...patch, campaignId } : patch;
    setLeads((current) => current.map((lead) => lead.id === id ? { ...lead, ...patch } : lead));
    setSavingIds((current) => new Set(current).add(id));
    try {
      const response = await fetch(`/api/leads/${encodeURIComponent(id)}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Failed to save CRM update.');
      setLeads((current) => current.map((lead) => lead.id === id ? { ...lead, ...payload.lead } : lead));
    } catch (err) {
      setLeads(before); setError(err.message);
    } finally {
      setSavingIds((current) => { const next = new Set(current); next.delete(id); return next; });
    }
  }

  const visibleLeads = useMemo(() => {
    const text = filters.text.trim().toLowerCase();
    return leads.filter((lead) => {
      if (text && !`${lead.name} ${lead.primary_type || ''} ${lead.phone || ''} ${lead.source_area || ''}`.toLowerCase().includes(text)) return false;
      if (filters.status !== 'All' && lead.status !== filters.status) return false;
      if (filters.priority !== 'All' && lead.priority !== filters.priority) return false;
      if (filters.hasPhone && !lead.phone) return false;
      if (filters.hasWebsite && !lead.website) return false;
      if (Number(lead.rating || 0) < Number(filters.minRating || 0)) return false;
      if (Number(lead.user_rating_count || 0) < Number(filters.minReviews || 0)) return false;
      return true;
    }).sort((a, b) => compareLeads(a, b, filters.sort));
  }, [leads, filters]);

  const selectedCampaign = campaigns.find((c) => c.id === campaignId);
  const stats = useMemo(() => ({
    total: leads.length,
    visible: visibleLeads.length,
    contacted: leads.filter((x) => x.status === 'Contacted').length,
    followUp: leads.filter((x) => x.status === 'Follow up').length,
    won: leads.filter((x) => x.status === 'Won').length,
  }), [leads, visibleLeads.length]);

  function exportCsv() {
    const rows = [['Campaign','Name','Type','Score','Rating','Reviews','Latest sampled review','Area','Status','Priority','Phone','Website','Google Maps','Qualification','Notes'], ...visibleLeads.map((lead) => [
      campaignId, lead.name, lead.primary_type, scoreOf(lead), lead.rating, lead.user_rating_count,
      lead.latest_sampled_review_at, lead.source_area, lead.status, lead.priority, lead.phone, lead.website,
      lead.google_maps_url, lead.qualification_reason, lead.notes,
    ])];
    const csv = rows.map((row) => row.map(csvEscape).join(',')).join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a'); a.href = url; a.download = `${campaignId || 'all'}-leads.csv`; a.click(); URL.revokeObjectURL(url);
  }

  return <main>
    <section className="hero compactHero">
      <div>
        <p className="eyebrow">Multi-campaign Lead CRM · Google Places + Cloudflare D1</p>
        <h1>{selectedCampaign?.name || 'Lead campaigns'}</h1>
        <p className="subcopy">One business identity, separate campaign qualification and CRM state. Google review freshness is a sampled signal from returned Places reviews.</p>
      </div>
      <div className="statGrid"><Stat label="Loaded" value={stats.total}/><Stat label="Visible" value={stats.visible}/><Stat label="Contacted" value={stats.contacted}/><Stat label="Follow up" value={stats.followUp}/><Stat label="Won" value={stats.won}/></div>
    </section>

    <section className="panel toolbar">
      <div className="toolbarTitle"><Filter size={18}/><strong>Campaign & pipeline filters</strong><span>{loading ? 'Loading D1...' : `${visibleLeads.length} shown`}</span></div>
      <div className="filterGrid">
        <label>Campaign<select value={campaignId} onChange={(e)=>setCampaignId(e.target.value)}><option value="">All / legacy leads</option>{campaigns.map(c=><option key={c.id} value={c.id}>{c.name} ({c.qualified_count || 0})</option>)}</select></label>
        <label>Search<div className="inputIcon"><Search size={16}/><input value={filters.text} onChange={(e)=>setFilters({...filters,text:e.target.value})} placeholder="name, area, type, phone"/></div></label>
        <label>Status<select value={filters.status} onChange={(e)=>setFilters({...filters,status:e.target.value})}><option>All</option>{STATUS_OPTIONS.map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Priority<select value={filters.priority} onChange={(e)=>setFilters({...filters,priority:e.target.value})}><option>All</option>{PRIORITY_OPTIONS.map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Min rating<select value={filters.minRating} onChange={(e)=>setFilters({...filters,minRating:e.target.value})}><option value="0">Any</option><option value="4">4.0+</option><option value="4.3">4.3+</option><option value="4.5">4.5+</option></select></label>
        <label>Min reviews<select value={filters.minReviews} onChange={(e)=>setFilters({...filters,minReviews:e.target.value})}><option value="0">Any</option><option value="10">10+</option><option value="25">25+</option><option value="50">50+</option><option value="100">100+</option></select></label>
        <label>Sort by<select value={filters.sort} onChange={(e)=>setFilters({...filters,sort:e.target.value})}><option value="score">Quality score</option><option value="freshness">Freshest sampled review</option><option value="rating">Rating</option><option value="reviews">Review count</option><option value="name">Name</option></select></label>
        <label className="checkboxLabel"><input type="checkbox" checked={filters.hasPhone} onChange={(e)=>setFilters({...filters,hasPhone:e.target.checked})}/>Has phone</label>
        <label className="checkboxLabel"><input type="checkbox" checked={filters.hasWebsite} onChange={(e)=>setFilters({...filters,hasWebsite:e.target.checked})}/>Has website</label>
        {campaignId && <label className="checkboxLabel"><input type="checkbox" checked={filters.qualifiedOnly} onChange={(e)=>setFilters({...filters,qualifiedOnly:e.target.checked})}/>Qualified only</label>}
      </div>
      <div className="toolbarActions"><button className="secondary" onClick={()=>setFilters(DEFAULT_FILTERS)}>Reset filters</button><button className="secondary" onClick={()=>{loadCampaigns();loadLeads();}}><RefreshCw size={16}/> Reload D1</button><button className="primary" onClick={exportCsv} disabled={!visibleLeads.length}><Download size={16}/> Export view</button></div>
    </section>

    {error && <div className="error">{error}</div>}
    <section className="panel tablePanel"><div className="tableWrap"><table><thead><tr><th>Lead</th><th>Score</th><th>Google proof</th><th>Freshness</th><th>Contact</th><th>Status</th><th>Priority</th><th>Notes</th><th>Links</th></tr></thead><tbody>
      {visibleLeads.map((lead)=><tr key={lead.id}>
        <td className="leadCell"><strong>{lead.name}</strong><span>{lead.primary_type || 'business'} · {lead.source_area || lead.address || ''}{savingIds.has(lead.id) ? ' · saving…' : ''}</span></td>
        <td><strong>{scoreOf(lead)}</strong><div className="muted">{lead.qualified === 0 ? 'Not qualified' : 'Qualified'}</div></td>
        <td className="rating"><Star size={14}/> {lead.rating || '—'} <span>({lead.user_rating_count || 0})</span></td>
        <td>{freshnessLabel(lead)}<div className="muted">sample {lead.recent_sampled_reviews ?? '—'}/5 recent</div></td>
        <td>{lead.phone ? <a className="phone" href={`tel:${lead.phone}`}><Phone size={14}/> {lead.phone}</a> : <span className="muted">No phone</span>}</td>
        <td><select value={lead.status || 'New'} onChange={(e)=>updateCrm(lead.id,{status:e.target.value})}>{STATUS_OPTIONS.map(x=><option key={x}>{x}</option>)}</select></td>
        <td><select value={lead.priority || 'Medium'} onChange={(e)=>updateCrm(lead.id,{priority:e.target.value})}>{PRIORITY_OPTIONS.map(x=><option key={x}>{x}</option>)}</select></td>
        <td><textarea value={lead.notes || ''} onChange={(e)=>setLeads((current)=>current.map((x)=>x.id===lead.id?{...x,notes:e.target.value}:x))} onBlur={(e)=>updateCrm(lead.id,{notes:e.target.value})} placeholder="owner, email, next step..."/></td>
        <td className="linkCell">{lead.website && <a href={lead.website} target="_blank" rel="noreferrer"><Globe2 size={15}/> Site</a>}{lead.google_maps_url && <a href={lead.google_maps_url} target="_blank" rel="noreferrer"><ExternalLink size={15}/> Maps</a>}</td>
      </tr>)}
      {!loading && !visibleLeads.length && <tr><td colSpan="9" className="empty">No leads match these filters.</td></tr>}
    </tbody></table></div></section>
  </main>;
}

function Stat({label,value}) { return <div className="stat"><strong>{value}</strong><span>{label}</span></div>; }
