import { GlobalWorkerOptions, TextLayer, getDocument, type PDFDocumentProxy } from 'pdfjs-dist/legacy/build/pdf.mjs';
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';
import { STATUS_TEXT } from './effective';
import { expand, njtUrl, ROLE_LABEL, shortName, summary, type Library, type Role, type Source, type SourceSet } from './sources';
import type { Citation } from './types';

GlobalWorkerOptions.workerSrc = workerUrl;

/** Whitespace-insensitive matching: PDF text items split words and lines unpredictably. */
const squash = (s: string) => s.normalize('NFC').replace(/\s+/g, '');

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

/** A paragraph's text without its own "24. § (1)" number. */
const snippetFull = (t: string) => t.replace(/^\s*(?:\d+(?:\/[A-Z])?\.\s*§\s*)?(?:\(\d+\)\s*)?/, '');

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
  private laidOut = false;
  /** 1 = page width fits the pane; more scrolls sideways (phones need it to read the text). */
  private zoom = 1;
  /** Set by the reader with − / +; until then the zoom follows the pane's width. */
  private manual = false;
  private resize: ResizeObserver;
  private timer = 0;
  /** Browsers drop the scroll position of a hidden box (another pane enlarged): remember it. */
  private saved: [number, number] = [0, 0];
  private wasHidden = false;
  private ready: Promise<void>;

  constructor(private readonly pagesEl: HTMLElement, url: string, private readonly cite: Citation | undefined,
    private readonly onMiss: (quote: string) => void) {
    this.ready = loadDoc(url).then(({ doc, sizes }) => { this.doc = doc; this.sizes = sizes; });
    // Lay out only once the pane is visible and has a width; again when it is enlarged or shrunk.
    pagesEl.addEventListener('scroll', () => {
      if (pagesEl.clientWidth) this.saved = [pagesEl.scrollTop, pagesEl.scrollLeft];
    }, { passive: true });
    this.resize = new ResizeObserver(() => {
      if (!pagesEl.clientWidth) {
        this.wasHidden = this.laidOut;
        return;
      }
      if (this.wasHidden) {
        this.wasHidden = false;
        [pagesEl.scrollTop, pagesEl.scrollLeft] = this.saved;
      }
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

  get currentZoom(): number {
    return this.zoom;
  }

  setZoom(zoom: number): void {
    this.zoom = zoom;
    this.manual = true;
    void this.layout();
  }

  private async layout(): Promise<void> {
    const fit = this.pagesEl.clientWidth - 16;
    // Regulation pages have wide margins: in a narrow pane start zoomed in on the text column.
    if (!this.manual && fit > 0) this.zoom = fit < 560 ? 1.4 : 1;
    const width = Math.floor(fit * this.zoom);
    if (fit <= 0 || Math.abs(width - this.width) < 8) return;
    await this.ready;
    const first = !this.laidOut;
    this.laidOut = true;
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
        this.pagesEl.scrollLeft += at.left - box.left - 12;
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
const ZOOMS = [0.7, 1, 1.4, 2, 3];

/** The overview groups sources by how they bear on the value, strongest first. */
const GROUPS: { title: string; roles: Role[] }[] = [
  { title: 'Ami itt érvényes', roles: ['cited', 'override', 'defines'] },
  { title: 'Alapérték', roles: ['table'] },
  { title: 'Értelmezés', roles: ['meaning'] },
  { title: 'Feltételes eltérések', roles: ['variant'] },
  { title: 'Országos előírások', roles: ['national'] },
  { title: 'Kapcsolódó bekezdések', roles: ['mention', 'reference'] },
  { title: 'Jogszabálytár', roles: ['web'] },
];

/** Numbers with units ("15,0 méter", "35%", "600 m2") stand out in a paragraph's text. */
function markNumbers(html: string): string {
  return html.replace(/\d+(?:[,.]\d+)?\s*(?:m2|m²|m&#178;|méter\p{L}*|m\b|%|százalék\p{L}*|szorzó\p{L}*)/gu, (m) => `<mark>${m}</mark>`);
}

/** The number of a value ("15,0 m" -> "15,0"), to find it in the paragraph. */
const valueNumber = (v?: string) => v?.match(/\d+(?:[,.]\d+)?/)?.[0];

/** Start the text at the clause that states the value, when that is far in (a long paragraph). */
function excerpt(text: string, value?: string): string {
  const n = valueNumber(value);
  const at = n ? text.search(new RegExp(`(?<![\\d,])${n.replace(/[.,]/g, '[.,]')}(?![\\d])`)) : -1;
  if (at < 160) return text;
  // Back up to the start of the clause: "c) ...", a semicolon or a sentence end.
  const head = text.slice(0, at);
  const start = Math.max(head.lastIndexOf('; '), head.lastIndexOf('. '), head.search(/\s[a-z]{1,2}\)\s[^)]*$/));
  return `… ${text.slice(start > 0 && at - start < 200 ? start + 1 : Math.max(0, at - 80)).trim()}`;
}

/** The source's own value gets a stronger mark than other numbers in the text. */
function markValue(html: string, value?: string): string {
  const n = valueNumber(value);
  return n ? html.replace(/<mark>([^<]*)<\/mark>/g, (m, t: string) => t.replace(/\s/g, '').startsWith(n) ? `<mark class="val">${t}</mark>` : m) : html;
}

interface Pane {
  el: HTMLElement;
  pdf?: PdfPane;
  zoom: number;
}

/**
 * Every source behind a value. The overview on the left lists them grouped by role, each with its
 * text, so the relations can be read without opening anything. The most important ones (the cited,
 * overriding and table sources) open as PDF panes on the right at their quotes; any other can be
 * opened next to them or enlarged alone. On phones the overview is the main screen and a source
 * opens full screen; the back button returns to the list.
 */
export class SourceViewer {
  private set?: SourceSet;
  private active = 0;
  private open_: number[] = [];
  private panes = new Map<number, Pane>();
  private readonly mobile = window.matchMedia('(max-width: 720px)');
  private readonly overviewEl: HTMLElement;
  private readonly panesEl: HTMLElement;

  constructor(private readonly root: HTMLElement, private readonly lib: Library) {
    root.innerHTML = `
      <header class="v-head">
        <button class="v-back" aria-label="Vissza a forrásokhoz">←</button>
        <div class="v-info"><div class="v-title"></div><div class="v-meta"></div></div>
        <button class="v-close" aria-label="Bezárás">×</button>
      </header>
      <div class="v-body">
        <nav class="v-overview" aria-label="Források"></nav>
        <div class="v-panes"><p class="v-empty">Válassz egy forrást a bal oldali listából.</p></div>
      </div>`;
    this.overviewEl = root.querySelector('.v-overview')!;
    this.panesEl = root.querySelector('.v-panes')!;
    root.querySelector('.v-close')!.addEventListener('click', () => this.close());
    root.querySelector('.v-back')!.addEventListener('click', () => history.state?.viewer === 'detail' ? history.back() : this.showList());
    document.addEventListener('keydown', (e) => this.onKey(e));
    // The phone's back button: first back to the list, then out of the viewer.
    window.addEventListener('popstate', (e) => {
      if (this.root.hidden) return;
      if (e.state?.viewer === 'list') this.showList();
      else if (!e.state?.viewer) this.closeNow();
    });
    new ResizeObserver(() => this.grid()).observe(this.panesEl);
    this.mobile.addEventListener('change', () => this.render());
  }

  /** Close, unwinding the history entries the viewer added. */
  close(): void {
    const depth = history.state?.viewer === 'detail' ? 2 : history.state?.viewer === 'list' ? 1 : 0;
    if (depth) history.go(-depth);
    else this.closeNow();
  }

  private closeNow(): void {
    this.root.hidden = true;
    document.body.classList.remove('viewer-open');
    this.panes.forEach((p) => { p.pdf?.destroy(); p.el.remove(); });
    this.panes.clear();
    this.open_ = [];
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

  /** Opens all sources of the set; `focus` (a citation in it) is selected and opened first. */
  open(set: SourceSet, focus?: Citation): void {
    this.panes.forEach((p) => { p.pdf?.destroy(); p.el.remove(); });
    this.panes.clear();
    this.set = expand(set, this.lib);
    const sources = this.set.sources;
    if (this.root.hidden) {
      this.root.hidden = false;
      document.body.classList.add('viewer-open');
      if (!history.state?.viewer) history.pushState({ ...history.state, viewer: 'list' }, '');
    }
    this.root.classList.remove('solo', 'detail');
    this.root.classList.toggle('multi', sources.length > 1);
    this.root.querySelector('.v-title')!.innerHTML = `${esc(this.set.title)}${this.set.value ? ` <b class="v-value">${esc(this.set.value)}</b>` : ''}`;
    this.root.querySelector('.v-meta')!.textContent = sources.length > 1 ? summary(this.set) : this.regMeta(sources[0]);

    const at = focus ? sources.findIndex((s) => s.cite && s.cite.reg === focus.reg && s.cite.para === focus.para) : -1;
    this.active = Math.max(at, 0);
    // Open what decides the value: the tapped source, what overrides here, and the table value.
    const want = [this.active, ...sources.flatMap((s, i) => ['cited', 'override', 'defines', 'table'].includes(s.role) ? [i] : [])];
    const max = window.innerWidth < 1100 ? 2 : 3;
    this.open_ = sources.length === 1 ? [0] : [...new Set(want)].slice(0, max);
    if (this.open_.length < 2 && sources.length > 1) this.open_ = [...new Set([...this.open_, ...sources.map((_, i) => i)])].slice(0, 2);
    this.render();
    // On a phone a single tapped citation goes straight to its document.
    if (this.mobile.matches && (sources.length === 1 || focus)) this.showDetail(this.active);
  }

  private regMeta(s: Source): string {
    const reg = this.lib.regs[s.cite?.reg ?? s.reg ?? ''];
    return reg ? [reg.decree, reg.effectiveFrom && `hatályos: ${reg.effectiveFrom}`, reg.retrievedAt && `letöltve: ${reg.retrievedAt}`].filter(Boolean).join(' · ') : '';
  }

  private where(s: Source): string {
    const regId = s.cite?.reg ?? s.reg;
    return s.cite ? `${shortName(s.cite.reg, this.lib.regs[s.cite.reg])} ${s.cite.para}` : regId ? shortName(regId, this.lib.regs[regId]) : s.title ?? '';
  }

  private link(s: Source): string | undefined {
    const reg = this.lib.regs[s.cite?.reg ?? s.reg ?? ''];
    return s.url ?? njtUrl(reg, s.cite?.para) ?? reg?.officialUrl;
  }

  private render(): void {
    const sources = this.set!.sources;
    const groups = GROUPS.map((g) => {
      const items = sources.map((s, i) => [s, i] as const).filter(([s]) => g.roles.includes(s.role));
      // Conditional variants: the ones that apply here first, the ones that do not last.
      const rank = { yes: 0, unknown: 1, no: 2 } as const;
      if (g.roles.includes('variant')) items.sort(([a], [b]) => rank[a.status ?? 'unknown'] - rank[b.status ?? 'unknown']);
      return items.length ? `<h4 class="o-group">${g.title}</h4><ol>${items.map(([s, i]) => this.card(s, i)).join('')}</ol>` : '';
    }).join('');
    this.overviewEl.innerHTML = `${sources.length > 1 ? `<p class="o-head">${sources.length} forrás<span class="o-count"></span></p>` : ''}${groups}
      <p class="o-keys muted small">↑ ↓ forrás választása · Enter megnyitás · F nagyítás · Esc vissza</p>`;
    // The whole card opens the source; its own links and buttons do their own thing.
    this.overviewEl.querySelectorAll<HTMLElement>('.o-card').forEach((c) =>
      c.addEventListener('click', (e) => {
        if (!(e.target as HTMLElement).closest('a, .o-pin, .o-more')) this.pick(Number(c.dataset.i));
      }));
    this.overviewEl.querySelectorAll<HTMLElement>('.o-pin').forEach((b) =>
      b.addEventListener('click', () => this.toggle(Number(b.dataset.i))));
    this.overviewEl.querySelectorAll<HTMLElement>('.o-more').forEach((b) =>
      b.addEventListener('click', () => {
        const card = b.closest('.o-card')!;
        card.classList.toggle('expanded');
        b.textContent = card.classList.contains('expanded') ? 'kevesebb' : 'teljes szöveg';
      }));
    this.renderPanes();
  }

  private card(s: Source, i: number): string {
    const status = s.status && s.role === 'variant' ? `<span class="o-status st-${s.status}">${esc(STATUS_TEXT[s.status])}</span>` : '';
    const body = s.text ? excerpt(snippetFull(s.text), s.value) : '';
    const long = body.length > 220;
    const link = this.link(s);
    return `<li class="o-card role-${s.role}${s.status === 'no' ? ' dim' : ''}" data-i="${i}">
      <button class="o-main" data-i="${i}" title="Megnyitás a dokumentumban">
        <span class="o-role">${ROLE_LABEL[s.role]}</span>
        <span class="o-where">${esc(this.where(s))}</span>
        ${s.value ? `<span class="o-value">${esc(s.value)}</span>` : ''}
      </button>
      ${s.note ? `<p class="o-note">${esc(s.note)}</p>` : ''}
      ${body ? `<p class="o-text${long ? ' clamp' : ''}">${markValue(markNumbers(esc(body)), s.value)}</p>` : ''}
      <div class="o-foot">${status}
        ${long ? '<button class="o-more">teljes szöveg</button>' : ''}
        ${this.set!.sources.length > 1 ? `<button class="o-pin" data-i="${i}"></button>` : ''}
        ${link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${link.includes('njt.jog.gov.hu') ? 'njt.hu' : 'Forrás'} ↗</a>` : ''}
      </div>
    </li>`;
  }

  /** Create panes for newly opened sources, drop closed ones, keep the rest (and their scroll). */
  private renderPanes(): void {
    for (const [i, p] of this.panes) {
      if (!this.open_.includes(i)) {
        p.pdf?.destroy();
        p.el.remove();
        this.panes.delete(i);
      }
    }
    for (const i of this.open_) {
      if (!this.panes.has(i)) this.panes.set(i, this.makePane(i));
      this.panesEl.append(this.panes.get(i)!.el); // keeps the open order
    }
    this.panesEl.querySelector('.v-empty')?.toggleAttribute('hidden', this.open_.length > 0);
    this.sync();
  }

  private makePane(i: number): Pane {
    const s = this.set!.sources[i];
    const regId = s.cite?.reg ?? s.reg;
    const reg = regId ? this.lib.regs[regId] : undefined;
    const link = this.link(s);
    const el = document.createElement('article');
    el.className = `pane role-${s.role}${reg?.pdf ? '' : ' web'}`;
    el.dataset.i = String(i);
    el.innerHTML = `<header class="p-head">
        <span class="p-role">${ROLE_LABEL[s.role]}</span>
        <span class="p-where" title="${esc(reg?.title ?? s.title ?? '')}${reg?.decree ? ` – ${esc(reg.decree)}` : ''}">${esc(this.where(s))}</span>
        ${s.value ? `<b class="p-value">${esc(s.value)}</b>` : ''}
        <span class="p-actions">
          ${reg?.pdf ? `<button class="p-btn p-out" aria-label="Kicsinyítés" title="Kicsinyítés">−</button><button class="p-btn p-in" aria-label="Nagyítás" title="Nagyobb betű">+</button>` : ''}
          ${link ? `<a href="${esc(link)}" target="_blank" rel="noopener" title="Hivatalos forrás (Nemzeti Jogszabálytár)">${link.includes('njt.jog.gov.hu') ? 'njt.hu' : 'Forrás'} ↗</a>` : ''}
          <button class="p-btn p-zoom" aria-label="Kinagyítás egyedül / vissza" title="Csak ez a forrás (F)"><span class="z-in">⤢</span><span class="z-out">⤡</span></button>
          <button class="p-btn p-close" aria-label="Bezárás" title="Bezárás">×</button>
        </span>
      </header>
      <p class="p-warn warn" hidden></p>
      ${reg?.pdf ? '<div class="v-pages"></div>' : `<div class="p-web">
        ${s.title ? `<h4>${esc(s.title)}</h4>` : ''}
        ${s.note ? `<p>${esc(s.note)}</p>` : ''}
        ${s.text ? `<blockquote>${markNumbers(esc(s.text))}</blockquote>` : ''}
        ${link ? `<a class="p-open" href="${esc(link)}" target="_blank" rel="noopener">Megnyitás a Nemzeti Jogszabálytárban ↗</a>
          <p class="muted small">A jogszabálytár nem engedi, hogy más oldalba ágyazva jelenjen meg, ezért új lapon nyílik meg.</p>` : ''}
      </div>`}`;
    const pane: Pane = { el, zoom: 1 };
    el.addEventListener('pointerdown', () => this.select(i));
    el.querySelector('.p-zoom')!.addEventListener('click', () => this.setSolo(!this.root.classList.contains('solo') || this.active !== i, i));
    el.querySelector('.p-close')!.addEventListener('click', (e) => {
      e.stopPropagation();
      if (this.mobile.matches) history.state?.viewer === 'detail' ? history.back() : this.showList();
      else this.toggle(i);
    });
    const step = (d: number) => {
      const now = pane.pdf?.currentZoom ?? pane.zoom;
      const at = d > 0 ? ZOOMS.findIndex((z) => z > now) : ZOOMS.map((z) => z < now).lastIndexOf(true);
      if (at < 0) return;
      pane.zoom = ZOOMS[at];
      pane.pdf?.setZoom(pane.zoom);
    };
    el.querySelector('.p-in')?.addEventListener('click', () => step(1));
    el.querySelector('.p-out')?.addEventListener('click', () => step(-1));
    const pages = el.querySelector<HTMLElement>('.v-pages');
    if (pages && reg?.pdf) {
      pane.pdf = new PdfPane(pages, `${import.meta.env.BASE_URL}${reg.pdf}`, s.cite, (quote) => {
        const warn = el.querySelector<HTMLElement>('.p-warn')!;
        warn.textContent = `A hivatkozott szöveg nem található a dokumentumban: „${quote}”`;
        warn.hidden = false;
      });
    }
    return pane;
  }

  /** A click on a source: open it next to the others (or alone on a phone) and bring it into view. */
  private pick(i: number): void {
    if (this.mobile.matches) return this.showDetail(i);
    if (!this.open_.includes(i)) {
      // Keep the grid readable: the oldest pane makes room once three are open in a narrow viewer.
      const max = this.panesEl.clientWidth < 2 * MIN_PANE_PX ? 2 : 4;
      this.open_ = [...this.open_, i].slice(-max);
      this.renderPanes();
    }
    this.select(i, true);
  }

  private toggle(i: number): void {
    if (this.open_.includes(i)) this.open_ = this.open_.filter((x) => x !== i);
    else this.open_ = [...this.open_, i];
    if (this.root.classList.contains('solo') && !this.open_.includes(this.active)) this.root.classList.remove('solo');
    this.renderPanes();
    if (this.open_.includes(i)) this.select(i, true);
  }

  private showDetail(i: number): void {
    this.open_ = [i];
    this.root.classList.add('detail');
    this.renderPanes();
    this.select(i);
    if (history.state?.viewer !== 'detail') history.pushState({ ...history.state, viewer: 'detail' }, '');
  }

  private showList(): void {
    this.root.classList.remove('detail');
    this.overviewEl.querySelector(`.o-card[data-i="${this.active}"]`)?.scrollIntoView({ block: 'nearest' });
  }

  /** Mark a source as current in the overview and among the panes. */
  private select(i: number, flash = false): void {
    this.active = i;
    this.sync();
    const pane = this.panes.get(i)?.el;
    if (flash && pane && !this.mobile.matches) {
      pane.scrollIntoView({ block: 'nearest' });
      pane.classList.remove('flash');
      void pane.offsetWidth;
      pane.classList.add('flash');
    }
  }

  private sync(): void {
    this.overviewEl.querySelectorAll<HTMLElement>('.o-card').forEach((c) => {
      const i = Number(c.dataset.i);
      c.classList.toggle('active', i === this.active);
      c.classList.toggle('opened', this.open_.includes(i));
      const pin = c.querySelector('.o-pin');
      if (pin) pin.textContent = this.open_.includes(i) ? 'bezárás' : 'megnyitás mellette';
    });
    const count = this.overviewEl.querySelector('.o-count');
    if (count) count.textContent = ` · ${this.open_.length} megnyitva`;
    this.panes.forEach((p, i) => p.el.classList.toggle('active', i === this.active));
    this.grid();
  }

  private setSolo(on: boolean, i = this.active): void {
    if (on && !this.open_.includes(i)) this.pick(i);
    this.select(i);
    this.root.classList.toggle('solo', on);
    this.grid();
  }

  private onKey(e: KeyboardEvent): void {
    if (this.root.hidden || (e.target as HTMLElement).closest('input, select, textarea')) return;
    const order = [...this.overviewEl.querySelectorAll<HTMLElement>('.o-card')].map((c) => Number(c.dataset.i));
    const at = order.indexOf(this.active);
    if (e.key === 'Escape') {
      if (this.root.classList.contains('solo')) this.setSolo(false);
      else if (this.root.classList.contains('detail')) history.state?.viewer === 'detail' ? history.back() : this.showList();
      else this.close();
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const next = order[Math.min(order.length - 1, Math.max(0, at + (e.key === 'ArrowDown' ? 1 : -1)))];
      this.select(next, true);
      // Focus follows, so Enter opens this card (not whatever button was focused before).
      this.overviewEl.querySelector<HTMLElement>(`.o-card[data-i="${next}"] .o-main`)?.focus({ preventScroll: true });
      this.overviewEl.querySelector(`.o-card[data-i="${next}"]`)?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter' && (e.target as HTMLElement).tagName !== 'BUTTON' && (e.target as HTMLElement).tagName !== 'A') {
      this.pick(this.active);
    } else if (e.key === 'f' || e.key === 'F') {
      this.setSolo(!this.root.classList.contains('solo'));
    }
  }

  /** Columns and rows for the pane grid: up to two rows fill the height, more rows scroll. */
  private grid(): void {
    const solo = this.root.classList.contains('solo') || this.mobile.matches;
    const n = solo ? 1 : Math.max(1, this.open_.length);
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
