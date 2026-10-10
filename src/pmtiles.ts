import maplibregl from 'maplibre-gl';
import { PMTiles, Protocol, type RangeResponse, type Source } from 'pmtiles';

/**
 * A PMTiles archive cut into fixed-size chunk files (scripts/pack_tiles.py): Workers static assets
 * ignore HTTP Range requests, so byte ranges are read from whole chunks, each fetched once.
 */
class ChunkedSource implements Source {
  private chunks = new Map<number, Promise<Uint8Array>>();

  constructor(private base: string, private size: number, private chunk: number) {}

  getKey(): string {
    return this.base;
  }

  private load(n: number): Promise<Uint8Array> {
    let p = this.chunks.get(n);
    if (!p) {
      p = fetch(`${this.base}/${n}.bin`).then((r) => {
        if (!r.ok) throw new Error(`${this.base}/${n}.bin: ${r.status}`);
        return r.arrayBuffer();
      }).then((b) => new Uint8Array(b));
      p.catch(() => this.chunks.delete(n)); // a failed fetch is retried next time
      this.chunks.set(n, p);
    }
    return p;
  }

  async getBytes(offset: number, length: number): Promise<RangeResponse> {
    const end = Math.min(offset + length, this.size);
    const first = Math.floor(offset / this.chunk);
    const last = Math.floor((end - 1) / this.chunk);
    const parts = await Promise.all(Array.from({ length: last - first + 1 }, (_, i) => this.load(first + i)));
    const out = new Uint8Array(Math.max(end - offset, 0));
    let at = 0;
    parts.forEach((part, i) => {
      const start = (first + i) * this.chunk;
      const slice = part.subarray(Math.max(offset - start, 0), Math.min(end - start, part.length));
      out.set(slice, at);
      at += slice.length;
    });
    return { data: out.buffer };
  }
}

let protocol: Protocol | undefined;

/** Registers a chunked archive and returns the tile URL template for a MapLibre raster source. */
export function chunkedPmtiles(base: string, size: number, chunk: number): string {
  if (!protocol) {
    protocol = new Protocol();
    maplibregl.addProtocol('pmtiles', protocol.tile);
  }
  protocol.add(new PMTiles(new ChunkedSource(base, size, chunk)));
  return `pmtiles://${base}/{z}/{x}/{y}`;
}
