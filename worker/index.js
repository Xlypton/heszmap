// Login check for every request, the tile proxy for the external overlays (src/overlays.ts), and dist/ behind both.
//
// The browser cannot load these services directly: none sends CORS headers, and the Budapest
// services only answer requests that come from their own ArcGIS apps (Referer). The proxy builds
// each upstream URL itself from the tile coordinates (no open relay), and caches every tile at the
// edge so the upstream services see as few requests as possible.
//
// LICENSING IS NOT CLEARED for any of these services (docs/data-sources.md): prototype use only.

const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36';
const OENY = { url: 'https://www.oeny.hu/hk-geoserver/hrsz/wms', referer: 'https://www.oeny.hu/oeny/hrsz-kereso/' };
const BP_REFERER = 'https://budapestkozut.maps.arcgis.com/';
const BP = 'https://utility.arcgis.com/usrsvcs/servers';
const BP_EXPORT = {
  frsz: `${BP}/1f424e22b69d4ea890228a42f375d9ce/rest/services/btp_frsz/frsz_2021/MapServer`,
  tszt: `${BP}/03ff87e7da1f48c39be230fb703540a4/rest/services/btp_tszt/tszt_2021/MapServer`,
  vi: `${BP}/35162649113d4ce494bb6a4129c763bf/rest/services/terezvaros/terezvaros_publikus/MapServer`,
};
const BP_ORTO = `${BP}/56e78bd6e8b14b51a9a18fb33e2fcbb6/rest/services/ortofoto/ortofoto_2024_2_rgb_wgs/MapServer`;
const OENY_LAYERS = { plots: 'hrsz:foldreszlet,hrsz:felirat_kat', buildings: 'hrsz:epulet' };
const MAX_AGE = 30 * 24 * 3600;

/** EPSG:3857 bounds of an XYZ tile. */
function tileBbox(z, x, y) {
  const size = (2 * Math.PI * 6378137) / 2 ** z;
  const o = Math.PI * 6378137;
  return [x * size - o, o - (y + 1) * size, (x + 1) * size - o, o - y * size].map((v) => v.toFixed(2)).join(',');
}

function upstream(source, rest, z, x, y) {
  const bbox = tileBbox(z, x, y);
  if (source === 'oeny' && OENY_LAYERS[rest]) {
    const q = new URLSearchParams({ service: 'WMS', version: '1.1.0', request: 'GetMap', layers: OENY_LAYERS[rest],
      styles: '', srs: 'EPSG:3857', bbox, width: '512', height: '512', format: 'image/png', transparent: 'true' });
    return [`${OENY.url}?${q}`, OENY.referer];
  }
  if (source === 'lechner' && /^20(0\d|1[0-5])$/.test(rest)) {
    // Only imagery 10+ years old is free to view at plot scale.
    const q = new URLSearchParams({ service: 'WMS', version: '1.3.0', request: 'GetMap', layers: `OrthoimageCoverage${rest}`,
      styles: '', crs: 'EPSG:3857', bbox, width: '512', height: '512', format: 'image/jpeg' });
    return [`https://inspire.lechnerkozpont.hu/geoserver/OI.${rest}/wms?${q}`, undefined];
  }
  if (source === 'bp' && rest === 'orto') return [`${BP_ORTO}/tile/${z}/${y}/${x}`, BP_REFERER];
  if (source === 'bp' && BP_EXPORT[rest]) {
    const q = new URLSearchParams({ bbox, bboxSR: '3857', imageSR: '3857', size: '512,512', format: 'png32',
      transparent: 'true', dpi: '96', f: 'image' });
    return [`${BP_EXPORT[rest]}/export?${q}`, BP_REFERER];
  }
  return [undefined, undefined];
}

async function proxy(request, ctx) {
  // /x/<source>/<variant>/<z>/<x>/<y>
  const m = new URL(request.url).pathname.match(/^\/x\/([a-z]+)\/([a-z0-9]+)\/(\d{1,2})\/(\d+)\/(\d+)$/);
  if (!m || request.method !== 'GET') return new Response('not found', { status: 404 });
  const [, source, rest, zs, xs, ys] = m;
  const [z, x, y] = [Number(zs), Number(xs), Number(ys)];
  if (z < 10 || z > 21 || x >= 2 ** z || y >= 2 ** z) return new Response('zoom out of range', { status: 400 });
  const [url, referer] = upstream(source, rest, z, x, y);
  if (!url) return new Response('unknown overlay', { status: 404 });

  const cache = caches.default;
  const key = new Request(new URL(request.url).origin + `/x/${source}/${rest}/${z}/${x}/${y}`);
  const hit = await cache.match(key);
  if (hit) return hit;

  const headers = { 'User-Agent': UA };
  if (referer) headers.Referer = referer;
  const res = await fetch(url, { headers });
  const type = res.headers.get('content-type') ?? '';
  if (!res.ok || !type.startsWith('image/')) {
    return new Response(`upstream ${res.status}`, { status: 502, headers: { 'Cache-Control': 'no-store' } });
  }
  const out = new Response(res.body, {
    headers: { 'Content-Type': type, 'Cache-Control': `public, max-age=${MAX_AGE}`, 'Access-Control-Allow-Origin': '*' },
  });
  ctx.waitUntil(cache.put(key, out.clone()));
  return out;
}

// Login in front of the whole site (static assets included: assets.run_worker_first is true).
// Credentials come from the Worker secrets AUTH_USER and AUTH_PASS; without them every request is
// refused, so a missing secret never leaves the site open. /login shows a form (with an error on a
// wrong login) and sets a session cookie: an HMAC of the username keyed by the password, so changing
// the password signs everyone out. A Basic Auth header is accepted too (curl -u user:pass).
const enc = new TextEncoder();
const COOKIE = 'hm_session';
const SESSION_DAYS = 30;

async function same(a, b) {
  const [ha, hb] = await Promise.all([a, b].map((v) => crypto.subtle.digest('SHA-256', enc.encode(v))));
  return crypto.subtle.timingSafeEqual(ha, hb);
}

async function credentialsOk(user, pass, env) {
  const [userOk, passOk] = await Promise.all([same(user, env.AUTH_USER), same(pass, env.AUTH_PASS)]);
  return userOk && passOk;
}

async function sessionToken(env) {
  const key = await crypto.subtle.importKey('raw', enc.encode(env.AUTH_PASS), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mac = await crypto.subtle.sign('HMAC', key, enc.encode(`heszmap-session:${env.AUTH_USER}`));
  return btoa(String.fromCharCode(...new Uint8Array(mac))).replace(/[+/=]/g, (c) => ({ '+': '-', '/': '_', '=': '' })[c]);
}

function cookie(request, name) {
  for (const part of (request.headers.get('Cookie') ?? '').split(';')) {
    const i = part.indexOf('=');
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return '';
}

async function authorized(request, env) {
  const session = cookie(request, COOKIE);
  if (session && (await same(session, await sessionToken(env)))) return true;
  const m = (request.headers.get('Authorization') ?? '').match(/^Basic\s+(\S+)$/i);
  if (!m) return false;
  let decoded;
  try {
    decoded = new TextDecoder().decode(Uint8Array.from(atob(m[1]), (c) => c.charCodeAt(0)));
  } catch {
    return false;
  }
  const i = decoded.indexOf(':');
  return i >= 0 && credentialsOk(decoded.slice(0, i), decoded.slice(i + 1), env);
}

/** Only same-site paths, so the login form cannot redirect elsewhere. */
function safeNext(next) {
  return typeof next === 'string' && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\') ? next : '/';
}

const escapeHtml = (v) => v.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function loginPage(next, error, status) {
  const html = `<!doctype html>
<html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bejelentkezés – HÉSZ térkép</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f4f5f7;
    font: 16px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; color: #1f2328; }
  form { width: min(320px, calc(100vw - 32px)); background: #fff; padding: 24px; border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,.12); display: grid; gap: 12px; }
  h1 { margin: 0 0 4px; font-size: 20px; }
  label { display: grid; gap: 4px; font-size: 14px; }
  input { font: inherit; padding: 8px 10px; border: 1px solid #c8ccd1; border-radius: 8px; }
  button { font: inherit; padding: 10px; border: 0; border-radius: 8px; background: #1f6feb; color: #fff; cursor: pointer; }
  .error { margin: 0; padding: 8px 10px; border-radius: 8px; background: #ffebe9; color: #b42318; font-size: 14px; }
</style></head><body>
<form method="post" action="/login">
  <h1>HÉSZ térkép</h1>
  ${error ? `<p class="error" role="alert">${escapeHtml(error)}</p>` : ''}
  <input type="hidden" name="next" value="${escapeHtml(next)}">
  <label>Felhasználónév <input name="user" autocomplete="username" required autofocus></label>
  <label>Jelszó <input name="pass" type="password" autocomplete="current-password" required></label>
  <button type="submit">Bejelentkezés</button>
</form></body></html>`;
  return new Response(html, { status, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });
}

async function login(request, env) {
  if (request.method !== 'POST') return loginPage(safeNext(new URL(request.url).searchParams.get('next')), '', 200);
  let form;
  try {
    form = await request.formData();
  } catch {
    return loginPage('/', 'Hibás kérés, próbáld újra.', 400);
  }
  const next = safeNext(form.get('next'));
  if (!(await credentialsOk(String(form.get('user') ?? ''), String(form.get('pass') ?? ''), env))) {
    return loginPage(next, 'Hibás felhasználónév vagy jelszó.', 401);
  }
  return new Response(null, {
    status: 303,
    headers: {
      Location: next,
      'Set-Cookie': `${COOKIE}=${await sessionToken(env)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_DAYS * 86400}`,
      'Cache-Control': 'no-store',
    },
  });
}

export default {
  async fetch(request, env, ctx) {
    if (!env.AUTH_USER || !env.AUTH_PASS) {
      return new Response('Login is not configured (set AUTH_USER and AUTH_PASS).', {
        status: 503, headers: { 'Cache-Control': 'no-store' },
      });
    }
    const { pathname, search } = new URL(request.url);
    if (pathname === '/login') return login(request, env);
    if (pathname === '/logout') {
      return new Response(null, {
        status: 303,
        headers: { Location: '/login', 'Set-Cookie': `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0` },
      });
    }
    if (!(await authorized(request, env))) {
      // Pages go to the login form; files the page loads (data, tiles) just get a 401.
      if (request.method === 'GET' && (request.headers.get('Accept') ?? '').includes('text/html')) {
        return new Response(null, {
          status: 302,
          headers: { Location: `/login?next=${encodeURIComponent(pathname + search)}`, 'Cache-Control': 'no-store' },
        });
      }
      return new Response('Login required', { status: 401, headers: { 'Cache-Control': 'no-store' } });
    }
    const url = new URL(request.url);
    if (url.pathname.startsWith('/x/')) return proxy(request, ctx);
    // Plan tiles from R2 (bucket "heszmap-tiles", binding TILES) once it is enabled: each municipality
    // adds ~2,500 files and a Worker's static assets are limited in file count. Needs the TILES
    // binding in wrangler.jsonc.
    if (url.pathname.startsWith('/tiles/') && env.TILES) {
      const obj = await env.TILES.get(url.pathname.slice(1)); // "tiles/<municipality>/<z>/<x>/<y>.webp"
      if (obj) {
        return new Response(obj.body, {
          headers: {
            'content-type': obj.httpMetadata?.contentType ?? 'image/webp',
            'cache-control': 'public, max-age=604800',
            etag: obj.httpEtag,
          },
        });
      }
      // Not uploaded yet: fall back to the static copy if the deployment still has one.
    }
    return env.ASSETS.fetch(request);
  },
};
