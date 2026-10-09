import { GlobalWorkerOptions, TextLayer, getDocument, type PDFDocumentProxy } from 'pdfjs-dist/legacy/build/pdf.mjs';
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';
import { STATUS_TEXT } from './effective';
import { expand, njtUrl, ROLE_LABEL, shortName, summary, type Library, type Source, type SourceSet } from './sources';
import type { Citation } from './types';

GlobalWorkerOptions.workerSrc = workerUrl;

/** Whitespace-insensitive matching: PDF text items split words and lines unpredictably. */
const squash = (s: string) => s.normalize('NFC').replace(/\s+/g, '');

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

/** The start of a paragraph, without its own "24. § (1)" number. */
const snippet = (t: string) => {
  const body = t.replace(/^\s*(?:\d+(?:\/[A-Z])?\.\s*§\s*)?(?:\(\d+\)\s*)?/, '');
  return body.length > 110 ? `${body.slice(0, 110).replace(/\s+\S*$/, '')}…` : body;
};

/** One loaded document per URL, shared by every pane that shows it (the same PDF can be open twice). */
const docs = new Map<string, Promise<{ doc: PDFDocumentProxy; sizes: [number, number][] }>>();

function loadDoc(url: string) {
  let p = docs.get(url);
  if (!p) {
    p = (async () => {
      const doc = await getDocument({ url }).promise;
      const sizes: [number, number][] = [];
      for (let n = 1; n <= doc.numPages; n++) {
        const vp = (await doc.getPage(n)).getViewport({ scale: 1 });
        sizes[n] = [vp.width, vp.height];
      }
      return { doc, sizes };
    })();
    docs.set(url, p);
    p.catch(() => docs.delete(url));
  }
  return p;
}

interface PageSlot {
  el: HTMLDivElement;
  rendered?: Promise<TextLayer>;
}

/** The pages of one PDF in a scrollable box, laid out to the box's width and scrolled to a quote. */
class PdfPane {
  private doc?: PDFDocumentProxy;
  private sizes: [number, number][] = [];
  private slots: PageSlot[] = [];
  private observer?: IntersectionObserver;
  private width = 0;
  private resize: ResizeObserver;
  private timer = 0;
  private ready: Promise<void>;

  constructor(private readonly pagesEl: HTMLElement, url: string, private readonly cite: Citation | undefined,
    private readonly onMiss: (quote: string) => void) {
    this.ready = loadDoc(url).then(({ doc, sizes }) => { this.doc = doc; this.sizes = sizes; });
    // Lay out only once the pane is visible and has a width; again when it is enlarged or shrunk.
    this.resize = new ResizeObserver(() => {
      clearTimeout(this.timer);
      this.timer = window.setTimeout(() => void this.layout(), this.width ? 150 : 0);
    });
    this.resize.observe(pagesEl);
  }

  destroy(): void {
    this.resize.disconnect();
    this.observer?.disconnect();
    clearTimeout(this.timer);
  }

  private async layout(): Promise<void> {
    const width = Math.floor(this.pagesEl.clientWidth - 16);
    if (width <= 0 || Math.abs(width - this.width) < 8) return;
    await this.ready;
    const first = !this.width;
    // Keep the reader's place when the pane is resized.
    const ratio = this.pagesEl.scrollHeight ? this.pagesEl.scrollTop / this.pagesEl.scrollHeight : 0;
    this.width = width;
    this.observer?.disconnect();
    this.pagesEl.innerHTML = '';
    this.slots = [];
    this.observer = new IntersectionObserver(
      (entries) => entries.filter((e) => e.isIntersecting).forEach((e) => void this.render(Number((e.target as HTMLElement).dataset.page))),
      { root: this.pagesEl, rootMargin: '400px 0px' },
    );
    for (let n = 1; n <= this.doc!.numPages; n++) {
      const [w, h] = this.sizes[n];
      const el = document.createElement('div');
      el.className = 'v-page';
      el.dataset.page = String(n);
      el.style.width = `${width}px`;
      el.style.height = `${(h * width) / w}px`;
      this.pagesEl.append(el);
      this.slots[n] = { el };
      this.observer.observe(el);
    }
    // Pages are rebuilt, so the highlight is too: bring the quote back into view.
    if (this.cite) await this.goTo(this.cite, first);
    else this.pagesEl.scrollTop = first ? 0 : ratio * this.pagesEl.scrollHeight;
  }

  private render(n: number): Promise<TextLayer> {
    const slot = this.slots[n];
    slot.rendered ??= (async () => {
      const page = await this.doc!.getPage(n);
      const width = parseFloat(slot.el.style.width);
      const scale = width / page.getViewport({ scale: 1 }).width;
      const vp = page.getViewport({ scale });
      const dpr = window.devicePixelRatio || 1;

      const canvas = document.createElement('canvas');
      canvas.width = Math.floor(vp.width * dpr);
      canvas.height = Math.floor(vp.height * dpr);
      canvas.style.width = `${vp.width}px`;
      canvas.style.height = `${vp.height}px`;
      const text = document.createElement('div');
      text.className = 'textLayer';
      slot.el.style.setProperty('--total-scale-factor', String(scale));
      slot.el.append(canvas, text);

      await page.render({ canvas, viewport: vp, transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined }).promise;
      const layer = new TextLayer({ textContentSource: page.streamTextContent(), container: text, viewport: vp });
      await layer.render();
      return layer;
    })();
    return slot.rendered;
  }

  /** The page number is only a hint: if the quote moved (e.g. a newer version), search all pages. */
  private async goTo(cite: Citation, report = true): Promise<void> {
    const total = this.doc!.numPages;
    const order = [cite.page, ...Array.from({ length: total }, (_, i) => i + 1).filter((n) => n !== cite.page)];
    for (const n of order) {
      if (n < 1 || n > total) continue;
      const hit = await this.highlight(n, cite.quote);
      if (hit) {
        // Centre the quote inside this pane only: scrollIntoView would also scroll the pane grid.
        const box = this.pagesEl.getBoundingClientRect(), at = hit.getBoundingClientRect();
        this.pagesEl.scrollTop += at.top - box.top - box.height / 3;
        return;
      }
    }
    this.pagesEl.scrollTop = this.slots[Math.min(Math.max(cite.page, 1), total)].el.offsetTop - 8;
    if (report) this.onMiss(cite.quote);
  }

  private async highlight(n: number, quote: string): Promise<HTMLElement | null> {
    const layer = await this.render(n);
    const items = layer.textContentItemsStr;
    const owner: number[] = [];
    let flat = '';
    items.forEach((s, i) => {
      const q = squash(s);
      flat += q;
      for (let k = 0; k < q.length; k++) owner.push(i);
    });
    const at = flat.indexOf(squash(quote));
    if (at < 0) return null;
    const hits = new Set(owner.slice(at, at + squash(quote).length));
    const divs = [...hits].map((i) => layer.textDivs[i]);
    divs.forEach((d) => d.classList.add('v-hl'));
    return divs[0] ?? null;
  }
}

/** Panes per row: as many as fit at a readable width. */
const MIN_PANE_PX = 380;

/**
 * Every source behind a value, side by side: an overview list on the left (what each source says
 * and how it relates), one pane per source on the right. A pane can be enlarged to fill the viewer.
 * On phones the overview is a strip of tabs and one pane shows at a time.
 */
export class SourceViewer {
  private panes: PdfPane[] = [];
  private set?: SourceSet;
  private active = 0;
  private readonly mobile = window.matchMedia('(max-width: 720px)');
  private readonly overviewEl: HTMLElement;
  private readonly panesEl: HTMLElement;

  constructor(private readonly root: HTMLElement, private readonly lib: Library) {
    root.innerHTML = `
      <header class="v-head">
        <div class="v-info"><div class="v-title"></div><div class="v-meta"></div></div>
        <button class="v-close" aria-label="Bezárás">×</button>
      </header>
      <div class="v-body">
        <nav class="v-overview" aria-label="Források"></nav>
        <div class="v-panes"></div>
      </div>`;
    this.overviewEl = root.querySelector('.v-overview')!;
    this.panesEl = root.querySelector('.v-panes')!;
    root.querySelector('.v-close')!.addEventListener('click', () => this.close());
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || root.hidden) return;
      if (root.classList.contains('solo') && !this.mobile.matches) this.setSolo(false);
      else this.close();
    });
    new ResizeObserver(() => this.grid()).observe(this.panesEl);
    this.mobile.addEventListener('change', () => this.select(this.active));
  }

  close(): void {
    this.root.hidden = true;
    document.body.classList.remove('viewer-open');
    this.panes.forEach((p) => p.destroy());
    this.panes = [];
    this.panesEl.innerHTML = '';
  }

  /** A whole regulation, from the top. */
  openRegulation(regId: string): void {
    const reg = this.lib.regs[regId];
    if (!reg?.pdf) {
      if (reg) window.open(reg.officialUrl, '_blank', 'noopener');
      return;
    }
    this.open({ title: reg.title, sources: [{ role: 'cited', reg: regId }] });
  }

  /** Opens all sources of the set; `focus` (a citation in it) is selected first. */
  open(set: SourceSet, focus?: Citation): void {
    this.close();
    this.set = expand(set, this.lib);
    const sources = this.set.sources;
    this.root.hidden = false;
    document.body.classList.add('viewer-open');
    this.root.querySelector('.v-title')!.innerHTML = `${esc(this.set.title)}${this.set.value ? ` <b class="v-value">${esc(this.set.value)}</b>` : ''}`;
    const meta = sources.length > 1 ? summary(this.set) : this.regMeta(sources[0]);
    this.root.querySelector('.v-meta')!.textContent = meta;
    this.root.classList.toggle('multi', sources.length > 1);

    this.overviewEl.innerHTML = `${sources.length > 1 ? `<p class="o-head">${sources.length} forrás</p>` : ''}
      <ol>${sources.map((s, i) => this.overviewItem(s, i)).join('')}</ol>`;
    this.overviewEl.querySelectorAll<HTMLElement>('[data-i]').forEach((b) =>
      b.addEventListener('click', () => this.select(Number(b.dataset.i), true)));

    this.panesEl.innerHTML = sources.map((s, i) => this.paneShell(s, i)).join('');
    this.panesEl.querySelectorAll<HTMLElement>('.p-zoom').forEach((b) =>
      b.addEventListener('click', () => {
        this.select(Number(b.dataset.i));
        this.setSolo(!this.root.classList.contains('solo'));
      }));
    sources.forEach((s, i) => {
      const pages = this.panesEl.querySelector<HTMLElement>(`.pane[data-i="${i}"] .v-pages`);
      const regId = s.cite?.reg ?? s.reg;
      const reg = regId ? this.lib.regs[regId] : undefined;
      if (!pages || !reg?.pdf) return;
      this.panes.push(new PdfPane(pages, `${import.meta.env.BASE_URL}${reg.pdf}`, s.cite, (quote) => {
        const warn = this.panesEl.querySelector<HTMLElement>(`.pane[data-i="${i}"] .p-warn`)!;
        warn.textContent = `A hivatkozott szöveg nem található a dokumentumban: „${quote}”`;
        warn.hidden = false;
      }));
    });

    const at = focus ? sources.findIndex((s) => s.cite && s.cite.reg === focus.reg && s.cite.para === focus.para && s.cite.quote === focus.quote) : -1;
    this.setSolo(false);
    this.select(Math.max(at, 0));
    this.grid();
  }

  private regMeta(s: Source): string {
    const reg = this.lib.regs[s.cite?.reg ?? s.reg ?? ''];
    return reg ? [reg.decree, reg.effectiveFrom && `hatályos: ${reg.effectiveFrom}`, reg.retrievedAt && `letöltve: ${reg.retrievedAt}`].filter(Boolean).join(' · ') : '';
  }

  private overviewItem(s: Source, i: number): string {
    const regId = s.cite?.reg ?? s.reg;
    const where = s.cite ? `${shortName(s.cite.reg, this.lib.regs[s.cite.reg])} ${s.cite.para}` : regId ? shortName(regId, this.lib.regs[regId]) : s.title ?? '';
    const status = s.status && s.role === 'variant' ? `<span class="o-status st-${s.status}">${esc(STATUS_TEXT[s.status])}</span>` : '';
    return `<li><button class="o-item role-${s.role}" data-i="${i}">
      <span class="o-role">${ROLE_LABEL[s.role]}</span>
      <span class="o-where">${esc(where)}</span>
      ${s.value ? `<span class="o-value">${esc(s.value)}</span>` : ''}
      ${s.note || s.text ? `<span class="o-note">${esc(s.note ?? snippet(s.text!))}</span>` : ''}${status}
    </button></li>`;
  }

  private paneShell(s: Source, i: number): string {
    const regId = s.cite?.reg ?? s.reg;
    const reg = regId ? this.lib.regs[regId] : undefined;
    const link = s.url ?? njtUrl(reg, s.cite?.para) ?? reg?.officialUrl;
    const where = s.cite ? `${shortName(s.cite.reg, reg)} · ${s.cite.para}` : reg ? shortName(regId!, reg) : s.title ?? '';
    const head = `<header class="p-head">
        <span class="p-role role-${s.role}">${ROLE_LABEL[s.role]}</span>
        <span class="p-where" title="${esc(reg?.title ?? s.title ?? '')}${reg?.decree ? ` – ${esc(reg.decree)}` : ''}">${esc(where)}</span>
        ${s.value ? `<b class="p-value">${esc(s.value)}</b>` : ''}
        <span class="p-actions">
          ${link ? `<a href="${esc(link)}" target="_blank" rel="noopener" title="Hivatalos forrás (Nemzeti Jogszabálytár)">${link.includes('njt.jog.gov.hu') ? 'njt.hu' : 'Forrás'} ↗</a>` : ''}
          <button class="p-zoom" data-i="${i}" aria-label="Nagyítás / vissza az áttekintéshez" title="Nagyítás"><span class="z-in">⤢</span><span class="z-out">⤡</span></button>
        </span>
      </header>
      <p class="p-warn warn" hidden></p>`;
    if (reg?.pdf) {
      return `<article class="pane role-${s.role}" data-i="${i}">${head}<div class="v-pages"></div></article>`;
    }
    // Web sources: njt.hu cannot be embedded (X-Frame-Options), so show what we know and link out.
    return `<article class="pane web role-${s.role}" data-i="${i}">${head}
      <div class="p-web">
        ${s.title ? `<h4>${esc(s.title)}</h4>` : ''}
        ${s.note ? `<p>${esc(s.note)}</p>` : ''}
        ${s.text ? `<blockquote>${esc(s.text)}</blockquote>` : ''}
        ${link ? `<a class="p-open" href="${esc(link)}" target="_blank" rel="noopener">Megnyitás a Nemzeti Jogszabálytárban ↗</a>
          <p class="muted small">A jogszabálytár nem engedi, hogy más oldalba ágyazva jelenjen meg, ezért új lapon nyílik meg.</p>` : ''}
      </div></article>`;
  }

  /** Mark a source as current: highlighted in the overview, shown on phones, scrolled to on desktop. */
  private select(i: number, fromOverview = false): void {
    this.active = i;
    this.overviewEl.querySelectorAll<HTMLElement>('[data-i]').forEach((b) => b.classList.toggle('active', Number(b.dataset.i) === i));
    this.panesEl.querySelectorAll<HTMLElement>('.pane').forEach((p) => p.classList.toggle('active', Number(p.dataset.i) === i));
    const pane = this.panesEl.querySelector<HTMLElement>(`.pane[data-i="${i}"]`);
    if (!pane) return;
    if (this.mobile.matches) {
      this.overviewEl.querySelector(`[data-i="${i}"]`)?.scrollIntoView({ inline: 'center', block: 'nearest' });
    } else if (fromOverview) {
      pane.scrollIntoView({ block: 'nearest' });
      pane.classList.remove('flash');
      void pane.offsetWidth;
      pane.classList.add('flash');
    }
  }

  private setSolo(on: boolean): void {
    this.root.classList.toggle('solo', on);
    this.grid();
  }

  /** Columns and rows for the pane grid: up to two rows fill the height, more rows scroll. */
  private grid(): void {
    const n = this.root.classList.contains('solo') || this.mobile.matches ? 1 : this.panesEl.children.length;
    const cols = Math.max(1, Math.min(n, Math.floor(this.panesEl.clientWidth / MIN_PANE_PX) || 1));
    const rows = Math.ceil(n / cols);
    this.panesEl.style.setProperty('--cols', String(cols));
    // Up to two rows share the height; with more, a bit of the third row peeks out to show it scrolls.
    const css = getComputedStyle(this.panesEl);
    const gap = parseFloat(css.rowGap) || 0;
    const h = this.panesEl.clientHeight - (parseFloat(css.paddingTop) || 0) - (parseFloat(css.paddingBottom) || 0);
    const r = rows <= 2 ? rows : 2.15;
    this.panesEl.style.setProperty('--row-h', `${Math.floor((h - gap * (Math.ceil(r) - 1)) / r)}px`);
  }
}
