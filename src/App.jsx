import { useEffect, useMemo, useState } from 'react';
import { Download, ExternalLink, Filter, Phone, RefreshCw, Search, Star } from 'lucide-react';

const CRM_KEY = 'qserve-leads-crm';
const STATUS_OPTIONS = ['New', 'Qualified', 'Contacted', 'Follow up', 'Won', 'Not fit'];
const PRIORITY_OPTIONS = ['High', 'Medium', 'Low'];
const PRICE_OPTIONS = [
  ['PRICE_LEVEL_MODERATE', '$$ Moderate'],
  ['PRICE_LEVEL_EXPENSIVE', '$$$ Expensive'],
  ['PRICE_LEVEL_VERY_EXPENSIVE', '$$$$ Very expensive'],
];

const DEFAULT_FILTERS = {
  text: '',
  status: 'All',
  priority: 'All',
  price: 'All',
  type: 'All',
  minRating: '0',
  hasPhone: false,
  sort: 'score',
};

function loadLocal(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function saveLocal(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function priceLabel(level) {
  if (level === 'PRICE_LEVEL_VERY_EXPENSIVE') return '$$$$';
  if (level === 'PRICE_LEVEL_EXPENSIVE') return '$$$';
  if (level === 'PRICE_LEVEL_MODERATE') return '$$';
  if (level === 'PRICE_LEVEL_INEXPENSIVE') return '$';
  return 'Unknown';
}

function typeBucket(lead) {
  const type = String(lead.primary_type || '').toLowerCase();
  const name = String(lead.name || '').toLowerCase();
  if (type.includes('coffee') || type.includes('cafe') || type.includes('bakery') || type.includes('donut') || name.includes('coffee') || name.includes('cafe')) {
    return 'Cafe';
  }
  return 'Restaurant';
}

function leadScore(lead) {
  const rating = Number(lead.rating || 0);
  const reviews = Number(lead.user_rating_count || 0);
  const priceBoost = lead.price_level === 'PRICE_LEVEL_VERY_EXPENSIVE' ? 30 : lead.price_level === 'PRICE_LEVEL_EXPENSIVE' ? 18 : 6;
  const phoneBoost = lead.phone ? 8 : 0;
  return Math.round(rating * 20 + Math.min(reviews, 3000) / 40 + priceBoost + phoneBoost);
}

function compareLeads(a, b, sort) {
  if (sort === 'rating') return Number(b.rating || 0) - Number(a.rating || 0);
  if (sort === 'reviews') return Number(b.user_rating_count || 0) - Number(a.user_rating_count || 0);
  if (sort === 'name') return a.name.localeCompare(b.name);
  if (sort === 'price') return priceRank(b.price_level) - priceRank(a.price_level);
  return leadScore(b) - leadScore(a);
}

function priceRank(level) {
  return level === 'PRICE_LEVEL_VERY_EXPENSIVE' ? 3 : level === 'PRICE_LEVEL_EXPENSIVE' ? 2 : level === 'PRICE_LEVEL_MODERATE' ? 1 : 0;
}

function csvEscape(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`;
}

export function App() {
  const [leads, setLeads] = useState([]);
  const [crm, setCrm] = useState(() => loadLocal(CRM_KEY, {}));
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    loadLeads();
  }, []);

  async function loadLeads() {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/noncheap_october_leads.json', { cache: 'no-store' });
      if (!response.ok) throw new Error('No generated leads file found yet. Run the GitHub Action once.');
      const payload = await response.json();
      setLeads(Array.isArray(payload) ? payload : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function updateCrm(leadId, patch) {
    const next = {
      ...crm,
      [leadId]: {
        status: 'New',
        priority: 'Medium',
        notes: '',
        ...(crm[leadId] || {}),
        ...patch,
        updatedAt: new Date().toISOString(),
      },
    };
    setCrm(next);
    saveLocal(CRM_KEY, next);
  }

  const enrichedLeads = useMemo(() => leads.map((lead) => ({
    ...lead,
    bucket: typeBucket(lead),
    score: leadScore(lead),
    crm: crm[lead.id] || { status: 'New', priority: 'Medium', notes: '' },
  })), [leads, crm]);

  const visibleLeads = useMemo(() => {
    const text = filters.text.trim().toLowerCase();
    return enrichedLeads
      .filter((lead) => {
        if (text) {
          const haystack = `${lead.name} ${lead.primary_type} ${lead.phone}`.toLowerCase();
          if (!haystack.includes(text)) return false;
        }
        if (filters.status !== 'All' && lead.crm.status !== filters.status) return false;
        if (filters.priority !== 'All' && lead.crm.priority !== filters.priority) return false;
        if (filters.price !== 'All' && lead.price_level !== filters.price) return false;
        if (filters.type !== 'All' && lead.bucket !== filters.type) return false;
        if (filters.hasPhone && !lead.phone) return false;
        if (Number(lead.rating || 0) < Number(filters.minRating || 0)) return false;
        return true;
      })
      .sort((a, b) => compareLeads(a, b, filters.sort));
  }, [enrichedLeads, filters]);

  const stats = useMemo(() => {
    const statuses = enrichedLeads.reduce((acc, lead) => {
      acc[lead.crm.status] = (acc[lead.crm.status] || 0) + 1;
      return acc;
    }, {});
    return {
      total: leads.length,
      visible: visibleLeads.length,
      contacted: statuses.Contacted || 0,
      followUp: statuses['Follow up'] || 0,
      won: statuses.Won || 0,
    };
  }, [enrichedLeads, leads.length, visibleLeads.length]);

  function exportCsv() {
    const headers = ['Name', 'Type', 'Status', 'Priority', 'Price', 'Rating', 'Reviews', 'Phone', 'Google Maps', 'Notes'];
    const rows = visibleLeads.map((lead) => [
      lead.name,
      lead.bucket,
      lead.crm.status,
      lead.crm.priority,
      priceLabel(lead.price_level),
      lead.rating,
      lead.user_rating_count,
      lead.phone,
      lead.google_maps_url,
      lead.crm.notes,
    ]);
    const csv = [headers, ...rows].map((row) => row.map(csvEscape).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'qserve-visible-leads.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main>
      <section className="hero compactHero">
        <div>
          <p className="eyebrow">QServe Outreach CRM</p>
          <h1>October & Sheikh Zayed leads pipeline.</h1>
          <p className="subcopy">
            Showing generated leads immediately. Filter the list, update outreach status, add notes, and export the current view.
          </p>
        </div>
        <div className="statGrid">
          <Stat label="All leads" value={stats.total} />
          <Stat label="Visible" value={stats.visible} />
          <Stat label="Contacted" value={stats.contacted} />
          <Stat label="Follow up" value={stats.followUp} />
          <Stat label="Won" value={stats.won} />
        </div>
      </section>

      <section className="panel toolbar">
        <div className="toolbarTitle">
          <Filter size={18} />
          <strong>Filter pipeline</strong>
          <span>{loading ? 'Loading leads...' : `${visibleLeads.length} of ${leads.length} shown`}</span>
        </div>
        <div className="filterGrid">
          <label>
            Search results
            <div className="inputIcon"><Search size={16} /><input value={filters.text} onChange={(e) => setFilters({ ...filters, text: e.target.value })} placeholder="name, type, phone" /></div>
          </label>
          <label>Status
            <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
              <option>All</option>{STATUS_OPTIONS.map((status) => <option key={status}>{status}</option>)}
            </select>
          </label>
          <label>Priority
            <select value={filters.priority} onChange={(e) => setFilters({ ...filters, priority: e.target.value })}>
              <option>All</option>{PRIORITY_OPTIONS.map((priority) => <option key={priority}>{priority}</option>)}
            </select>
          </label>
          <label>Price
            <select value={filters.price} onChange={(e) => setFilters({ ...filters, price: e.target.value })}>
              <option value="All">All non-cheap</option>{PRICE_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          <label>Type
            <select value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })}>
              <option>All</option><option>Cafe</option><option>Restaurant</option>
            </select>
          </label>
          <label>Min rating
            <select value={filters.minRating} onChange={(e) => setFilters({ ...filters, minRating: e.target.value })}>
              <option value="0">Any</option><option value="4">4.0+</option><option value="4.3">4.3+</option><option value="4.5">4.5+</option>
            </select>
          </label>
          <label>Sort by
            <select value={filters.sort} onChange={(e) => setFilters({ ...filters, sort: e.target.value })}>
              <option value="score">Lead score</option><option value="price">Highest price</option><option value="rating">Rating</option><option value="reviews">Reviews</option><option value="name">Name</option>
            </select>
          </label>
          <label className="checkboxLabel">
            <input type="checkbox" checked={filters.hasPhone} onChange={(e) => setFilters({ ...filters, hasPhone: e.target.checked })} />
            Has phone
          </label>
        </div>
        <div className="toolbarActions">
          <button type="button" className="secondary" onClick={() => setFilters(DEFAULT_FILTERS)}>Reset filters</button>
          <button type="button" className="secondary" onClick={loadLeads}><RefreshCw size={16} /> Reload JSON</button>
          <button type="button" className="primary" onClick={exportCsv} disabled={!visibleLeads.length}><Download size={16} /> Export view</button>
        </div>
      </section>

      {error && <div className="error">{error}</div>}

      <section className="panel tablePanel">
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Lead</th>
                <th>Price</th>
                <th>Rating</th>
                <th>Phone</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Notes</th>
                <th>Links</th>
              </tr>
            </thead>
            <tbody>
              {visibleLeads.map((lead) => (
                <tr key={lead.id}>
                  <td className="leadCell">
                    <strong>{lead.name}</strong>
                    <span>{lead.bucket} · {lead.primary_type || 'venue'} · score {lead.score}</span>
                  </td>
                  <td><span className={`priceBadge p${priceRank(lead.price_level)}`}>{priceLabel(lead.price_level)}</span></td>
                  <td className="rating"><Star size={14} /> {lead.rating || '—'} <span>({lead.user_rating_count || 0})</span></td>
                  <td>{lead.phone ? <a className="phone" href={`tel:${lead.phone}`}><Phone size={14} /> {lead.phone}</a> : <span className="muted">No phone</span>}</td>
                  <td>
                    <select value={lead.crm.status} onChange={(e) => updateCrm(lead.id, { status: e.target.value })}>
                      {STATUS_OPTIONS.map((status) => <option key={status}>{status}</option>)}
                    </select>
                  </td>
                  <td>
                    <select value={lead.crm.priority} onChange={(e) => updateCrm(lead.id, { priority: e.target.value })}>
                      {PRIORITY_OPTIONS.map((priority) => <option key={priority}>{priority}</option>)}
                    </select>
                  </td>
                  <td>
                    <textarea value={lead.crm.notes || ''} onChange={(e) => updateCrm(lead.id, { notes: e.target.value })} placeholder="owner, WhatsApp, next step..." />
                  </td>
                  <td className="linkCell">
                    {lead.google_maps_url && <a href={lead.google_maps_url} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Maps</a>}
                  </td>
                </tr>
              ))}
              {!loading && !visibleLeads.length && (
                <tr><td colSpan="8" className="empty">No leads match these filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function Stat({ label, value }) {
  return <div className="stat"><strong>{value}</strong><span>{label}</span></div>;
}
