# UI Design Law — Trading Engine Platform

## Absolute Rules — No Exceptions

### Colors — ONLY these 4:
- **Black** `#0A0A0A` — background, cards, borders
- **White** `#FFFFFF` — all text, headings, values, labels
- **Green** `#22C55E` — BUY, profit, positive, READY, RUNNING
- **Red** `#EF4444` — SELL, loss, negative, CLOSE, stopped

### Grey Scale — ONLY for inactive/secondary:
- `#555` — inactive tab text, secondary labels (like "Stop Loss", "Trail Stop")
- `#333` — dimmed/empty dashes, closed markets text
- `#222` — empty cell placeholders
- `#1A1A1A` — borders, card outlines
- `#111` — row hover, subtle dividers

### BANNED Colors:
- NO gold/amber `#D4A843` `#706030`
- NO yellow `#F59E0B`
- NO blue `#3B82F6`
- NO purple
- NO orange
- NO teal
- NO ANY other color ever

### Font Sizes — Minimum readable:
- Headings/titles: `text-base` (16px) or `text-sm` (14px) minimum
- Values (prices, P&L, stats): `text-sm` (14px) or `text-base` (16px)
- Labels (Win Rate, Trades, etc): `text-[10px]` minimum, `font-bold`, `uppercase`
- Table data: `text-[11px]` minimum
- Table headers: `text-[9px]` minimum, `font-extrabold`, `uppercase`
- NOTHING below `text-[9px]` ever

### Text Weight:
- All headings: `font-extrabold`
- All values: `font-extrabold`
- All labels: `font-bold`
- No thin/light/normal weight text

### Layout:
- Max width `1400px`, centered with `mx-auto`
- Table sort locked — refresh once per 12 hours, not per tick
- No grey pipe `|` separators between tabs
- Buttons must be solid colored and obviously clickable
