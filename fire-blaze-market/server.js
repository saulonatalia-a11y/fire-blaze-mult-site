'use strict';
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, 'index.html'));
const port = Number(process.env.PORT) || 10000;
const base = 'https://poke.idleworld.online';
const interval = Math.max(30000, Number(process.env.POLL_MS) || 60000);
let state = { connected: false, updatedAt: null, listings: [], message: 'Aguardando sessão autorizada de leitura.' };
let previous = new Map();
let changes = [];
let running = false;
function clean(v) { return typeof v === 'string' ? v.slice(0, 200) : v; }
function normalize(x) {
  if (!x || typeof x !== 'object') return null;
  const kind = String(x.kind || x.category || '').toLowerCase().includes('pokemon') || x.speciesId != null ? 'pokemon' : 'item';
  return {
    id: String(x.id ?? (Array.isArray(x.ids) ? x.ids.join(',') : x.refId ?? '')),
    kind, name: clean(x.name || ''), seller: clean(Array.isArray(x.sellers) ? x.sellers.join(', ') : x.seller || ''),
    price: Number.isFinite(Number(x.price)) ? Number(x.price) : null,
    currency: clean(x.currency || 'Gold'), quantity: Number(x.quantity) || 1,
    iv: x.ivTotal == null ? null : Number(x.ivTotal), quality: clean(x.quality || ''),
    shiny: Boolean(x.shiny), level: x.level == null ? null : Number(x.level),
    category: clean(x.category || ''), icon: clean(x.icon || ''),
    offerOnly: Boolean(x.offerOnly), at: clean(x.at || '')
  };
}
async function gameGet(url, token) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(url, {
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/json' },
      signal: controller.signal
    });
    if (!res.ok) throw new Error('Market API HTTP ' + res.status);
    return await res.json();
  } finally { clearTimeout(timer); }
}
async function poll() {
  if (running) return;
  const token = process.env.GAME_ACCESS_TOKEN;
  if (!token) {
    state = { ...state, connected: false, message: 'Sessão de leitura não configurada no Render.' };
    return;
  }
  running = true;
  try {
    // The game's All response contains the full non-Pokémon listings array.
    // Pokemon is a separate paginated endpoint, with query parameters still to be validated.
    const payload = await gameGet(base + '/api/game/market?category=All', token);
    if (!Array.isArray(payload.listings)) throw new Error('Formato de anúncios inesperado');
    const listings = payload.listings.map(normalize).filter(x => x && x.id);
    const next = new Map(listings.map(x => [x.id, x]));
    const now = new Date().toISOString();
    if (state.updatedAt) {
      for (const [id, item] of next) {
        const old = previous.get(id);
        if (!old) changes.unshift({ type: 'added', id, name: item.name, at: now });
        else if (JSON.stringify(old) !== JSON.stringify(item)) changes.unshift({ type: 'changed', id, name: item.name, at: now });
      }
      for (const [id, item] of previous) if (!next.has(id)) changes.unshift({ type: 'removed', id, name: item.name, at: now });
      changes = changes.slice(0, 300);
    }
    previous = next;
    state = { connected: true, updatedAt: now, listings, message: 'Dados reais sincronizados. Pokémon paginados ainda não incluídos.' };
  } catch (err) {
    state = { ...state, connected: false, message: String(err.message || err).slice(0, 160) };
    console.error('Market read failed:', state.message);
  } finally { running = false; }
}
const server = http.createServer((req, res) => {
  if (req.method !== 'GET') { res.writeHead(405); return res.end(); }
  const pathname = new URL(req.url, 'http://localhost').pathname;
  if (pathname === '/api/market' || pathname === '/api/events') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': 'same-origin' });
    return res.end(JSON.stringify(pathname === '/api/events' ? { events: changes } : state));
  }
  if (pathname === '/' || pathname === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    return res.end(html);
  }
  res.writeHead(404); res.end('Not found');
});
server.listen(port, '0.0.0.0', () => console.log('FIRE BLAZE Market on port', port));
poll();
setInterval(poll, interval);
