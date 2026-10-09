// Tile proxy for the external overlays (src/overlays.ts); everything else is served from dist/.
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

export default {
  async fetch(request, env, ctx) {
    if (new URL(request.url).pathname.startsWith('/x/')) return proxy(request, ctx);
    return env.ASSETS.fetch(request);
  },
};
