// Bottom sheet for phones: drag the handle/top strip between three snap points, or tap to cycle.
type Snap = 'peek' | 'half' | 'full';

const PEEK_PX = 150; // handle + search + layer toggle
const HALF = 0.55;
const FULL = 0.9;

export class BottomSheet {
  private snap: Snap = 'peek';
  private readonly mq = window.matchMedia('(max-width: 720px)');

  constructor(private readonly panel: HTMLElement, grip: HTMLElement) {
    let startY = 0;
    let startOffset = 0;
    let moved = false;
    let active = false;

    const onDown = (e: PointerEvent) => {
      if (!this.mq.matches || (e.target as HTMLElement).closest('input, button:not(#sheet-handle), select, label')) return;
      active = true;
      moved = false;
      startY = e.clientY;
      startOffset = this.offset(this.snap);
      panel.classList.add('dragging');
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    };
    const onMove = (e: PointerEvent) => {
      if (!active) return;
      const dy = e.clientY - startY;
      if (Math.abs(dy) > 6) moved = true;
      const y = Math.min(Math.max(startOffset + dy, this.offset('full')), this.offset('peek'));
      panel.style.setProperty('--sheet-y', `${y}px`);
    };
    const onUp = (e: PointerEvent) => {
      if (!active) return;
      active = false;
      panel.classList.remove('dragging');
      if (!moved) {
        this.set(this.snap === 'peek' ? 'half' : this.snap === 'half' ? 'full' : 'peek');
        return;
      }
      // Snap to the nearest point, biased by the drag direction.
      const y = startOffset + (e.clientY - startY);
      const order: Snap[] = ['full', 'half', 'peek'];
      const nearest = order.reduce((a, b) => (Math.abs(this.offset(b) - y) < Math.abs(this.offset(a) - y) ? b : a));
      this.set(nearest);
    };
    grip.addEventListener('pointerdown', onDown);
    grip.addEventListener('pointermove', onMove);
    grip.addEventListener('pointerup', onUp);
    grip.addEventListener('pointercancel', onUp);
    window.addEventListener('resize', () => this.set(this.snap));
    this.mq.addEventListener('change', () => this.set(this.snap));
    this.set('peek');
  }

  /** translateY of the sheet (its full height is FULL × viewport) for a snap point. */
  private offset(s: Snap): number {
    const h = window.innerHeight * FULL;
    if (s === 'full') return 0;
    if (s === 'half') return h - window.innerHeight * HALF;
    return h - PEEK_PX;
  }

  set(s: Snap): void {
    this.snap = s;
    this.panel.dataset.snap = s;
    this.panel.style.setProperty('--sheet-y', this.mq.matches ? `${this.offset(s)}px` : '0px');
    document.getElementById('sheet-handle')?.setAttribute('aria-expanded', String(s !== 'peek'));
  }

  /** Visible height of the sheet, for keeping the map's focus point above it. */
  visibleHeight(): number {
    return this.mq.matches ? window.innerHeight * FULL - this.offset(this.snap) : 0;
  }
}
