// Serves plan tiles from R2 (bucket "heszmap-tiles", binding TILES); everything else is the static
// site (dist/, binding ASSETS). Tiles live in R2 because each municipality adds ~2,500 files and a
// Worker's static assets are limited in file count.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/tiles/') && env.TILES) {
      const key = url.pathname.slice(1); // "tiles/<municipality>/<z>/<x>/<y>.webp"
      const obj = await env.TILES.get(key);
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
