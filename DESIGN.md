# Design

The visual world for The Record.

The client pinned this to the **Medium design system** (styles.refero.design),
rebased on **#133955** as the sole hue. The structure is Medium's; the colour is
the client's.

## Colour and the credibility bands

The reference forbids chromatic colour in UI: *"no blue links, no green buttons,
no red errors."* That is awkward here, because the product's centrepiece is a
Credibility Score with four bands, and four bands invite a green/amber/red badge.

We kept the prohibition. A publication that colour-codes its own trustworthiness
ends up looking like a browser security warning, so an instrument reading suits
the product better anyway. Every credibility state is encoded three ways, none of
them colour:

1. fill length, for the quantity
2. ink value, for the band, as weight within one hue
3. the band word, always rendered, and always the authority

`Disputed` also switches to a hatched fill, so the most consequential state
survives grayscale printing and colour-blind vision.

For the same reason there is no red error state anywhere. Errors are marked by a
full-weight rule and an icon, and they carry `role="alert"` so the urgency
reaches a screen reader, which a colour never did.

## Palette

One hue (205 degrees) at ten lightnesses. Nothing on screen is a true gray, so
the shadows in the paper are the same colour as the ink in the type. Contrast was
computed rather than eyeballed. Ratios are against `--canvas` / `--paper`.

| Token      | Value     | Use                          | Contrast      |
| ---------- | --------- | ---------------------------- | ------------- |
| `--paper`  | `#fcfdfd` | cards, article body          | n/a           |
| `--canvas` | `#f2f5f8` | the page: stock, not white   | n/a           |
| `--sunken` | `#e5ecf0` | wells, meter troughs         | n/a           |
| `--hair`   | `#ccd8e0` | default 1px rule             | n/a           |
| `--rule`   | `#9ab1c1` | emphatic divider, meter ticks| 2.03, **non-text only** |
| `--mute`   | `#587184` | captions, metadata           | 4.67 / 5.01   |
| `--quiet`  | `#446074` | secondary text               | 6.05 / 6.50   |
| `--body`   | `#294c65` | running body copy            | 8.29 / 8.90   |
| `--ink`    | `#133955` | headings, primary (brand)    | 11.00 / 11.82 |
| `--deep`   | `#0a2233` | filled buttons only          | 15.98         |

Every text token clears WCAG AA. `--rule` does not, so it must never carry text.
The inspection pass catches it if it ever does.

Surfaces are separated by a shift in colour value plus a hairline. There is no
`box-shadow` in this system.

## Type

| Role    | Face                | Why                                              |
| ------- | ------------------- | ------------------------------------------------ |
| Display | Playfair Display    | the reference's own named fallback for GT Super  |
| UI      | Inter               | its named fallback for Söhne                     |
| Body    | Source Serif 4      | a transitional book serif cut for screen reading |

Self-hosted via `@fontsource` rather than a CDN, so the pages render identically
offline and nothing third-party runs on first paint.

Minor-third scale from a 16px base. Display sizes are fluid (`clamp`) so the
masthead never overflows at 360px, which the reference's fixed 120px would.

## Shape and motion

Pills for actions (`9999px`), square corners for anything holding content (`0`).
The contrast between those two shapes carries the shape language, so softening
cards to 8px would erase it.

One curve throughout, `cubic-bezier(0.16, 1, 0.3, 1)`, an exponential ease-out.
There is one authored moment: the article reading column settles upward a few
pixels on load, starting from an already-visible default so nothing is hidden if
the animation never runs. Everything else is state feedback under 260ms.

## Structural rules

The front page is laid out as a newspaper front rather than a card grid: one lead
article at display scale, then a ruled index. Identical cards would flatten the
hierarchy the scores create. Listings follow the same idea and use rules rather
than boxes, because a newspaper index reads down a column.

The score travels with the reader, in a sticky margin column on the article page
that folds above the body below 64rem.

Tables stack below 46rem. A four-column table on a phone is either clipped or a
swipe nobody discovers, so each row becomes a block instead.

Links are typographic: the same colour as body text, underlined on hover. Colour
carries no meaning anywhere in this system.

The filled button is the only solid ink on a page. One per view, on the action
that view exists for.

## Browser surfaces

These are themed rather than left to the OS: text selection, caret,
`accent-color`, scrollbars (both WebKit and Firefox), `:focus-visible` rings,
underline offset, tabular numerals in every table and score, and Safari's
search-field decorations.

## Verification

`frontend/shots.mjs` captures all ten surfaces at 1440 and 390 in one pass and
reports console errors, failed requests, unscrollable overflow, and any text
failing WCAG AA. Run it against a live backend:

```bash
node shots.mjs
```

It measures overflow on `body.scrollWidth` rather than `documentElement`.
Chromium's `documentElement.scrollWidth` counts content inside scroll containers
the user can never reach, and reports a correctly-scrolling table as a page
defect.

## Surface modes

| Surface                        | Mode      |
| ------------------------------ | --------- |
| Front page, article, search    | Read      |
| How scoring works              | Persuade  |
| Sign in, register              | Operate   |
| Your writing, review queue     | Operate   |
