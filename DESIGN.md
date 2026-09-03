# Design

The visual world for The Record.

Pinned by the client to the **Medium design system** (styles.refero.design) —
"a cream-colored broadsheet at golden hour" — rebased on **#133955** as the sole
hue. The structure is Medium's; the ink is the client's.

## The one decision everything else follows

The reference forbids chromatic colour in UI: *"no blue links, no green buttons,
no red errors."* This product's centrepiece is a Credibility Score with four
bands, which invites a green–amber–red badge.

We kept the prohibition, and it produced a better answer than the one we would
have reached without it. **A publication that colour-codes its own
trustworthiness looks like a browser security warning.** An instrument reading
looks like a masthead. Every credibility state is encoded three ways, none of
them colour:

1. **fill length** — the quantity
2. **ink value** — the band, as weight within one hue
3. **the band word** — always rendered, always the authority

`Disputed` additionally switches to a hatched fill, so the most consequential
state survives grayscale printing and colour-blind vision.

This is also why there is no red error state anywhere: errors are marked by a
full-weight rule and an icon, and carry `role="alert"` so the urgency reaches a
screen reader — which a colour never did.

## Palette

One hue (205°) at ten lightnesses. Nothing on screen is a true gray, so the
shadows in the paper are the same colour as the ink in the type. Contrast was
computed, not eyeballed; ratios are against `--canvas` / `--paper`.

| Token      | Value     | Use                          | Contrast      |
| ---------- | --------- | ---------------------------- | ------------- |
| `--paper`  | `#fcfdfd` | cards, article body          | —             |
| `--canvas` | `#f2f5f8` | the page — stock, not white  | —             |
| `--sunken` | `#e5ecf0` | wells, meter troughs         | —             |
| `--hair`   | `#ccd8e0` | default 1px rule             | —             |
| `--rule`   | `#9ab1c1` | emphatic divider, meter ticks| 2.03 — **non-text only** |
| `--mute`   | `#587184` | captions, metadata           | 4.67 / 5.01   |
| `--quiet`  | `#446074` | secondary text               | 6.05 / 6.50   |
| `--body`   | `#294c65` | running body copy            | 8.29 / 8.90   |
| `--ink`    | `#133955` | headings, primary — **brand**| 11.00 / 11.82 |
| `--deep`   | `#0a2233` | filled buttons only          | 15.98         |

Every text token clears WCAG AA. `--rule` does not and must never carry text —
that mistake was made once and caught by the inspection pass.

**Elevation is a value shift, never a shadow.** There is no `box-shadow` in this
system. Surfaces separate by colour value plus a hairline.

## Type

| Role    | Face                | Why                                              |
| ------- | ------------------- | ------------------------------------------------ |
| Display | Playfair Display    | the reference's own named fallback for GT Super  |
| UI      | Inter               | its named fallback for Söhne                     |
| Body    | Source Serif 4      | a transitional book serif cut for screen reading |

Self-hosted via `@fontsource`, not a CDN: the pages render identically offline
and nothing third-party runs on first paint.

Minor-third scale from a 16px base. Display sizes are fluid (`clamp`) so the
masthead never overflows at 360px — the reference's fixed 120px would.

## Shape and motion

Pills for actions (`9999px`), square for anything holding content (`0`). The
contrast between the two *is* the shape language; softening cards to 8px would
erase it.

One curve — `cubic-bezier(0.16, 1, 0.3, 1)`, exponential ease-out. **One
authored moment:** the article reading column settles upward a few pixels on
load, from an already-visible default so nothing is hidden if the animation
never runs. Everything else is state feedback under 260ms.

## Structural rules

- **The front page is a newspaper front, not a card grid.** One lead article at
  display scale, then a ruled index. Identical cards would flatten exactly the
  hierarchy the scores create.
- **Listings are rules, not boxes.** A newspaper index reads down a column.
- **The score travels with the reader** — sticky margin column on the article
  page, folding above the body below 64rem.
- **Tables stack below 46rem.** A four-column table on a phone is either clipped
  or a swipe nobody discovers; each row becomes a block instead.
- **Links are typographic.** Same colour as body text, underline on hover. In
  this world colour carries no meaning at all.
- **The filled button is the only solid ink on a page.** One per view, on the
  action that view exists for.

## Browser surfaces

Themed, not left to the OS: text selection, caret, `accent-color`, scrollbars
(both WebKit and Firefox), `:focus-visible` rings, underline offset, tabular
numerals in every table and score, and Safari's search-field decorations.

## Verification

`frontend/shots.mjs` captures all ten surfaces at 1440 and 390 in one pass and
reports console errors, failed requests, unscrollable overflow, and any text
failing WCAG AA. Run it against a live backend:

```bash
node shots.mjs
```

It measures overflow on `body.scrollWidth`, not `documentElement` — Chromium's
`documentElement.scrollWidth` counts content inside scroll containers the user
can never reach, and reports a correctly-scrolling table as a page defect.

## Surface modes

| Surface                        | Mode      |
| ------------------------------ | --------- |
| Front page, article, search    | Read      |
| How scoring works              | Persuade  |
| Sign in, register              | Operate   |
| Your writing, review queue     | Operate   |
