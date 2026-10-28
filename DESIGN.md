# Design

The visual world for Sterling Wire.

Refined and premium, the way a quality weekly is: a cool porcelain page,
graphite type, generous air, photographs given room. The client approved this
direction from a mock-up of the home and article pages; it replaces the earlier
Medium-based look, keeping the client's navy (#133955) as the accent.

## Colour and the credibility bands

A publication that colour-codes its own trustworthiness ends up looking like a
browser security warning, so there is no green/amber/red anywhere. The score is
Sterling Wire's one bold mark: a **ring**, a hairline track with the reading drawn
round it in navy and the numeral set inside, like the gauge on an instrument.
Every reading is encoded three ways, none of them colour alone:

1. the arc's length round the ring, for the quantity
2. the numeral, for the exact score
3. the band word, always rendered, and always the authority

`Disputed` also dashes the ring's track, so the most consequential state
survives grayscale printing and colour-blind vision.

There is still no red error state. Errors are marked by a full-weight rule and
an icon, and carry `role="alert"`.

## Palette

Cool neutrals, never cream: "sterling" is silver. Contrast ratios are against
`--canvas` / `--paper`.

| Token      | Value     | Use                               | Contrast      |
| ---------- | --------- | --------------------------------- | ------------- |
| `--paper`  | `#ffffff` | panels, inputs, lifted things     | n/a           |
| `--canvas` | `#f4f5f6` | the page: porcelain, not white    | n/a           |
| `--sunken` | `#edeff1` | wells, footer, meter troughs      | n/a           |
| `--hair`   | `#d3d8dd` | silver hairline                   | n/a           |
| `--rule`   | `#a9b2ba` | emphatic divider, ring dashes     | **non-text only** |
| `--mute`   | `#5b6772` | captions, metadata                | 5.3 / 5.7     |
| `--quiet`  | `#4a5560` | secondary text, standfirsts       | 7.0 / 7.6     |
| `--body`   | `#2a3640` | running body copy                 | 11.6 / 12.6   |
| `--ink`    | `#18232d` | headings, primary text            | 14.6 / 15.9   |
| `--deep`   | `#133955` | filled buttons                    | 12.1 on white |
| `--accent` | `#133955` | links that act, the ring, focus   | 10.9 / 11.8   |

Surfaces are separated by a shift in value plus a hairline. There is no
`box-shadow` in this system.

## Type

| Role          | Face            | Why                                                   |
| ------------- | --------------- | ----------------------------------------------------- |
| Display, body | Newsreader      | drawn for news; light at large optical sizes for headlines, a sturdy reading face below |
| UI            | Hanken Grotesk  | navigation, bylines and metadata, in sentence case    |

One serif family carries both headlines and reading, set light (300) and large
for headlines; the grotesque does the interface. Labels are sentence case, never
letterspaced capitals. Self-hosted via `@fontsource-variable` (Newsreader with
its optical-size axis), so nothing third-party runs on first paint. Chinese text
falls back to the system's serif and sans faces.

## Shape and motion

Pills for actions (`9999px`), square corners for anything holding content (`0`).
The contrast between those two shapes carries the shape language, so softening
cards to 8px would erase it.

One curve throughout, `cubic-bezier(0.16, 1, 0.3, 1)`, an exponential ease-out.
There is one authored moment: the article reading column settles upward a few
pixels on load, starting from an already-visible default so nothing is hidden if
the animation never runs. Everything else is state feedback under 260ms.

## Structural rules

The masthead has two tiers: a dateline, the wordmark centred and the account at
the top; the sections on a ruled line beneath, followed by the tools for writers
and editors. It is not sticky. On phones the dateline goes and the section line
scrolls sideways.

The front page is a quality paper's front rather than a card grid: the lead story
with a large photograph and its ring, three top stories with photographs, then the
latest as a ruled list beside a short note on what the rings mean.

The article is one centred column. The headline block and the reading column
share a measure; only the photograph runs wider. The score sits in the byline as
a ring and opens out after the text into the full breakdown and its sources.

Tables stack below 46rem. A four-column table on a phone is either clipped or a
swipe nobody discovers, so each row becomes a block instead.

Headline links are the colour of the text and turn navy on hover; links that act
("How this was scored") are navy with a hairline underline. Colour never carries
meaning on its own.

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

| Surface                                     | Mode      |
| ------------------------------------------- | --------- |
| Front page, article, search, section         | Read      |
| Writer profile                               | Read      |
| How scoring works, subscriptions and pricing | Persuade  |
| Sign in, register, reset password            | Operate   |
| Your writing, the article editor             | Operate   |
| Review queue, flagged content                | Operate   |
| Your account, administration                 | Operate   |

Sixteen screens in total. The Operate surfaces outnumber the rest because five
of the six roles are here to do a job rather than to read.

## Patterns that recur

A few shapes carry most of the interface, and reusing them is deliberate: a
reader who learns one screen has learned several.

- **Tabs for a role's whole job.** Administration and Your account both hold six
  or more unrelated tasks. Tabs rather than one long page, because someone
  arrives with one task in mind and should not scroll past five others.
- **A ruled list for anything reviewable.** The review queue, flagged content,
  and the dispute queue are the same block: the item, the evidence, and the
  decision, with the consequence stated before the button rather than after.
- **Status as a word.** Draft, pending, published, unpublished, retracted. Never
  a coloured dot, so the state survives grayscale and reaches a screen reader.
- **The destructive action names what it destroys.** "Delete" on a draft,
  "Unpublish" on a live article, because the same endpoint does both and only
  one is irreversible.
