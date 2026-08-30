import { useMemo, useState } from 'react';
import { ExternalLink, MapPin, Phone, Search, Star, StickyNote, Globe2 } from 'lucide-react';

const DEFAULT_CENTER = { lat: 29.9724785, lng: 30.9576332 };
const STATUS_OPTIONS = ['New', 'Qualified', 'Contacted', 'Follow up', 'Won', 'Not fit'];
const PRICE_OPTIONS = [
  ['PRICE_LEVEL_INEXPENSIVE', '$'],
  ['PRICE_LEVEL_MODERATE', '$$'],
  ['PRICE_LEVEL_EXPENSIVE', '$$$'],
  ['PRICE_LEVEL_VERY_EXPENSIVE', '$$$$'],
];

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
  const match = PRICE_OPTIONS.find(([value]) => value === level);
  return match ? match[1] : 'Unknown';
}

function scoreLead(place) {
  const rating = Number(place.rating || 0);
  const reviews = Number(place.userRatingCount || 0);
  const price = place.priceLevel === 'PRICE_LEVEL_EXPENSIVE' ? 1 : place.priceLevel === 'PRICE_LEVEL_VERY_EXPENSIVE' ? 2 : 0;
  return Math.round(rating * 20 + Math.min(reviews, 1000) / 20 + price * 15);
}

export function App() {
  const [filters, setFilters] = useState({
    query: 'cafe OR restaurant',
    type: 'cafe',
    lat: DEFAULT_CENTER.lat,
    lng: DEFAULT_CENTER.lng,
    radius: 5000,
    priceLevels: ['PRICE_LEVEL_EXPENSIVE', 'PRICE_LEVEL_VERY_EXPENSIVE'],
  });
  const [places, setPlaces] = useState([]);
  const [crm, setCrm] = useState(() => loadLocal('qserve-leads-crm', {}));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const stats = useMemo(() => {
    const saved = Object.values(crm);
    return {
      total: places.length,
      contacted: saved.filter((item) => item.status === 'Contacted').length,
      followUp: saved.filter((item) => item.status === 'Follow up').length,
      won: saved.filter((item) => item.status === 'Won').length,
    };
  }, [places.length, crm]);

  async function runSearch(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(filters),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Search failed');
      const ranked = (payload.places || [])
        .map((place) => ({ ...place, leadScore: scoreLead(place) }))
        .sort((a, b) => b.leadScore - a.leadScore);
      setPlaces(ranked);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function updateCrm(placeId, patch) {
    const next = {
      ...crm,
      [placeId]: {
        status: 'New',
        notes: '',
        priority: 'Medium',
        ...(crm[placeId] || {}),
        ...patch,
        updatedAt: new Date().toISOString(),
      },
    };
    setCrm(next);
    saveLocal('qserve-leads-crm', next);
  }

  function togglePrice(level) {
    const next = filters.priceLevels.includes(level)
      ? filters.priceLevels.filter((item) => item !== level)
      : [...filters.priceLevels, level];
    setFilters({ ...filters, priceLevels: next });
  }

  function exportCsv() {
    const rows = [
      ['Name', 'Status', 'Priority', 'Price', 'Rating', 'Reviews', 'Phone', 'Website', 'Maps', 'Address', 'Notes'],
      ...places.map((place) => {
        const row = crm[place.id] || {};
        return [
          place.displayName?.text || '',
          row.status || 'New',
          row.priority || 'Medium',
          priceLabel(place.priceLevel),
          place.rating || '',
          place.userRatingCount || '',
          place.nationalPhoneNumber || '',
          place.websiteUri || '',
          place.googleMapsUri || '',
          place.formattedAddress || '',
          row.notes || '',
        ];
      }),
    ];
    const csv = rows.map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'qserve-leads.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main>
      <section className="hero">
        <div>
          <p className="eyebrow">QServe outreach CRM</p>
          <h1>Find premium cafés and restaurants, then track your sales outreach.</h1>
          <p className="subcopy">
            Built for QServe lead sourcing. Search Google Places, filter by price level, qualify leads, add notes, and export your outreach list.
          </p>
        </div>
        <div className="statGrid">
          <Stat label="Results" value={stats.total} />
          <Stat label="Contacted" value={stats.contacted} />
          <Stat label="Follow up" value={stats.followUp} />
          <Stat label="Won" value={stats.won} />
        </div>
      </section>

      <form className="panel filters" onSubmit={runSearch}>
        <label>
          Search query
          <input value={filters.query} onChange={(e) => setFilters({ ...filters, query: e.target.value })} />
        </label>
        <label>
          Place type
          <select value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })}>
            <option value="cafe">Cafés</option>
            <option value="restaurant">Restaurants</option>
          </select>
        </label>
        <label>
          Latitude
          <input type="number" step="any" value={filters.lat} onChange={(e) => setFilters({ ...filters, lat: e.target.value })} />
        </label>
        <label>
          Longitude
          <input type="number" step="any" value={filters.lng} onChange={(e) => setFilters({ ...filters, lng: e.target.value })} />
        </label>
        <label>
          Radius meters
          <input type="number" min="500" max="50000" value={filters.radius} onChange={(e) => setFilters({ ...filters, radius: e.target.value })} />
        </label>
        <div className="priceBox">
          <span>Price filters</span>
          <div className="chips">
            {PRICE_OPTIONS.map(([value, label]) => (
              <button key={value} type="button" className={filters.priceLevels.includes(value) ? 'chip active' : 'chip'} onClick={() => togglePrice(value)}>
                {label}
              </button>
            ))}
          </div>
        </div>
        <button className="primary" disabled={loading}>
          <Search size={18} /> {loading ? 'Searching...' : 'Search leads'}
        </button>
        <button type="button" className="secondary" onClick={exportCsv} disabled={!places.length}>Export CSV</button>
      </form>

      {error && <div className="error">{error}</div>}

      <section className="leadGrid">
        {places.map((place) => (
          <LeadCard key={place.id} place={place} crm={crm[place.id] || {}} updateCrm={updateCrm} />
        ))}
      </section>
    </main>
  );
}

function Stat({ label, value }) {
  return <div className="stat"><strong>{value}</strong><span>{label}</span></div>;
}

function LeadCard({ place, crm, updateCrm }) {
  const name = place.displayName?.text || 'Unnamed venue';
  return (
    <article className="card">
      <div className="cardTop">
        <div>
          <h2>{name}</h2>
          <p className="address"><MapPin size={14} /> {place.formattedAddress || 'No address returned'}</p>
        </div>
        <div className="score">{place.leadScore}</div>
      </div>
      <div className="meta">
        <span>{priceLabel(place.priceLevel)}</span>
        <span><Star size={14} /> {place.rating || '—'} ({place.userRatingCount || 0})</span>
        <span>{place.businessStatus || 'Status unknown'}</span>
      </div>
      <div className="links">
        {place.nationalPhoneNumber && <a href={`tel:${place.nationalPhoneNumber}`}><Phone size={15} /> Call</a>}
        {place.websiteUri && <a href={place.websiteUri} target="_blank" rel="noreferrer"><Globe2 size={15} /> Website</a>}
        {place.googleMapsUri && <a href={place.googleMapsUri} target="_blank" rel="noreferrer"><ExternalLink size={15} /> Maps</a>}
      </div>
      <div className="crmControls">
        <label>Status
          <select value={crm.status || 'New'} onChange={(e) => updateCrm(place.id, { status: e.target.value })}>
            {STATUS_OPTIONS.map((status) => <option key={status}>{status}</option>)}
          </select>
        </label>
        <label>Priority
          <select value={crm.priority || 'Medium'} onChange={(e) => updateCrm(place.id, { priority: e.target.value })}>
            <option>High</option><option>Medium</option><option>Low</option>
          </select>
        </label>
      </div>
      <label className="notes"><StickyNote size={15} /> Notes
        <textarea value={crm.notes || ''} onChange={(e) => updateCrm(place.id, { notes: e.target.value })} placeholder="Decision maker, Instagram, WhatsApp, next step..." />
      </label>
    </article>
  );
}
