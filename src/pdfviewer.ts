import { GlobalWorkerOptions, TextLayer, getDocument, type PDFDocumentLoadingTask, type PDFDocumentProxy } from 'pdfjs-dist/legacy/build/pdf.mjs';
import workerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url';
import 'pdfjs-dist/web/pdf_viewer.css';
import type { Citation, Regulation } from './types';

GlobalWorkerOptions.workerSrc = workerUrl;

/** Whitespace-insensitive matching: PDF text items split words and lines unpredictably. */
const squash = (s: string) => s.normalize('NFC').replace(/\s+/g, '');

interface PageSlot {
  el: HTMLDivElement;
  rendered?: Promise<TextLayer>;
}

export class PdfViewer {
  private task?: PDFDocumentLoadingTask;
  private doc?: PDFDocumentProxy;
  private docUrl?: string;
  private slots: PageSlot[] = [];
  private observer?: IntersectionObserver;
  private readonly pagesEl: HTMLElement;

  constructor(private readonly root: HTMLElement) {
    root.innerHTML = `
      <header class="v-head">
        <div class="v-info"><div class="v-title"></div><div class="v-meta"></div></div>
        <a class="v-official" target="_blank" rel="noopener">Hivatalos forrás ↗</a>
        <button class="v-close" aria-label="Bezárás">×</button>
      </header>
      <div class="v-status"></div>
      <div class="v-pages"></div>`;
    this.pagesEl = root.querySelector('.v-pages')!;
    root.querySelector('.v-close')!.addEventListener('click', () => this.close());
    document.addEventListener('keydown', (e) => e.key === 'Escape' && this.close());
  }

  close(): void {
    this.root.hidden = true;
    document.body.classList.remove('viewer-open');
  }

  async open(reg: Regulation, cite?: Citation): Promise<void> {
    if (!reg.pdf) {
      window.open(reg.officialUrl, '_blank', 'noopener');
      return;
    }
    this.root.hidden = false;
    document.body.classList.add('viewer-open');
    this.root.querySelector('.v-title')!.textContent = reg.title;
    const meta = [reg.decree, reg.effectiveFrom && `hatályos: ${reg.effectiveFrom}`, reg.retrievedAt && `letöltve: ${reg.retrievedAt}`];
    this.root.querySelector('.v-meta')!.textContent = meta.filter(Boolean).join(' · ');
    this.root.querySelector<HTMLAnchorElement>('.v-official')!.href = reg.officialUrl;
    this.setStatus(cite ? `${cite.para} – „${cite.quote}”` : '');

    const url = `${import.meta.env.BASE_URL}${reg.pdf}`;
    if (this.docUrl !== url) await this.load(url);
    if (cite) await this.goTo(cite);
    else this.pagesEl.scrollTop = 0;
  }

  private setStatus(text: string, warn = false): void {
    const el = this.root.querySelector<HTMLElement>('.v-status')!;
    el.textContent = text;
    el.hidden = !text;
    el.classList.toggle('warn', warn);
  }

  private async load(url: string): Promise<void> {
    this.observer?.disconnect();
    await this.task?.destroy();
    this.pagesEl.innerHTML = '';
    this.slots = [];
    this.docUrl = url;
    this.task = getDocument({ url });
    this.doc = await this.task.promise;

    const width = this.pagesEl.clientWidth - 24;
    this.observer = new IntersectionObserver(
      (entries) => entries.filter((e) => e.isIntersecting).forEach((e) => this.render(Number((e.target as HTMLElement).dataset.page))),
      { root: this.pagesEl, rootMargin: '400px 0px' },
    );
    for (let n = 1; n <= this.doc.numPages; n++) {
      const page = await this.doc.getPage(n);
      const vp = page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width });
      const el = document.createElement('div');
      el.className = 'v-page';
      el.dataset.page = String(n);
      el.style.width = `${vp.width}px`;
      el.style.height = `${vp.height}px`;
      this.pagesEl.append(el);
      this.slots[n] = { el };
      this.observer.observe(el);
    }
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
  private async goTo(cite: Citation): Promise<void> {
    this.pagesEl.querySelectorAll('.v-hl').forEach((el) => el.classList.remove('v-hl'));
    const order = [cite.page, ...Array.from({ length: this.doc!.numPages }, (_, i) => i + 1).filter((n) => n !== cite.page)];
    for (const n of order) {
      if (n < 1 || n > this.doc!.numPages) continue;
      const hit = await this.highlight(n, cite.quote);
      if (hit) {
        hit.scrollIntoView({ block: 'center' });
        return;
      }
    }
    this.slots[Math.min(Math.max(cite.page, 1), this.doc!.numPages)].el.scrollIntoView({ block: 'start' });
    this.setStatus(`A hivatkozott szöveg nem található a dokumentumban: „${cite.quote}”`, true);
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
