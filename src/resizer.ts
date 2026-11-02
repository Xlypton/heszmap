// Desktop: drag the strip on the panel's right edge to change the side panel's width.
// Double-click (or Home key) resets it; arrow keys nudge it. The width is remembered per browser.

const STORE = 'heszmap.panelWidth';
const DEFAULT_W = 360;
const MIN_W = 280;
const maxW = () => Math.max(MIN_W, Math.min(900, window.innerWidth - 320));
const clamp = (w: number) => Math.round(Math.min(Math.max(w, MIN_W), maxW()));

export function initPanelResizer(handle: HTMLElement, onResize: () => void): void {
  const root = document.documentElement;
  let width = DEFAULT_W;
  let frame = 0;

  const apply = (w: number, persist = false) => {
    width = clamp(w);
    root.style.setProperty('--panel-w', `${width}px`);
    handle.setAttribute('aria-valuenow', String(width));
    if (!frame) frame = requestAnimationFrame(() => { frame = 0; onResize(); });
    if (persist) {
      try { localStorage.setItem(STORE, String(width)); } catch { /* storage blocked: not remembered */ }
    }
  };

  handle.setAttribute('aria-valuemin', String(MIN_W));
  handle.setAttribute('aria-valuemax', '900');
  let stored = NaN;
  try { stored = Number(localStorage.getItem(STORE)); } catch { /* ignore */ }
  apply(Number.isFinite(stored) && stored > 0 ? stored : DEFAULT_W);

  let startX = 0;
  let startW = 0;
  handle.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    startX = e.clientX;
    startW = width;
    handle.setPointerCapture(e.pointerId);
    document.body.classList.add('resizing');
  });
  handle.addEventListener('pointermove', (e) => {
    if (!handle.hasPointerCapture(e.pointerId)) return;
    apply(startW + e.clientX - startX);
  });
  const end = (e: PointerEvent) => {
    if (!handle.hasPointerCapture(e.pointerId)) return;
    handle.releasePointerCapture(e.pointerId);
    document.body.classList.remove('resizing');
    apply(width, true);
  };
  handle.addEventListener('pointerup', end);
  handle.addEventListener('pointercancel', end);
  handle.addEventListener('dblclick', () => apply(DEFAULT_W, true));
  handle.addEventListener('keydown', (e) => {
    const step = e.shiftKey ? 60 : 20;
    if (e.key === 'ArrowLeft') apply(width - step, true);
    else if (e.key === 'ArrowRight') apply(width + step, true);
    else if (e.key === 'Home') apply(DEFAULT_W, true);
    else return;
    e.preventDefault();
  });
  // Keep the panel inside the window when the window shrinks.
  window.addEventListener('resize', () => { if (width > maxW()) apply(width); });
}
