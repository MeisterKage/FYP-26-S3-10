# Product

## Platform

web

## Stack

React (Vite) SPA · Flask REST API · PostgreSQL via Supabase. Committed in PDD §2.1
and §2.2; the database is a team decision recorded in the project README. Flask is
the single entry point — no client ever queries the database directly.

## Users

Six tiers, from PDD §1 and PRD §1.3.2:

- **Unregistered visitor** — reads public articles, browses categories, sees
  credibility scores, cannot comment or publish.
- **Free registered reader** — comments, likes, follows, saves reading lists, sets
  category interests, reports inaccuracies, applies to contribute.
- **Premium registered reader** — the above plus subscriber-only articles.
- **Verified contributor** — drafts, submits, and schedules articles; tags
  verifiable sources; tracks their Accuracy Rate and earnings.
- **Editor** — reviews and approves submissions **within an assigned content
  category only**, moderates flagged content, issues corrections.
- **System administrator** — account governance, contributor applications,
  categories, platform-wide scoring thresholds, dispute resolution, logs.

The context that matters: a reader deciding, in seconds, whether to trust an
article by someone they have never heard of.

## Product Purpose

A news publishing platform where every article carries a **Credibility Score** and
every contributor an **Accuracy Rate**, both produced by a fixed, disclosed formula
rather than a hidden or predictive model. Success is a reader who can trace exactly
why a score is what it is.

## Positioning

The disclosure itself. Competitors either hide their ranking (algorithmic feeds) or
have none (open publishing). PRD §1.3.3 and PDD §1 commit to arithmetic a reader can
follow: contributor accuracy, a fixed value per verifiable source link, a fixed
penalty per correction or retraction, and a further penalty once reader reports pass
an administrator-set threshold. Every input is published. A neighbouring product
cannot copy the claim without also publishing its formula.

## Operating Context

- Articles move draft → submitted → editor review → published, with corrections and
  retractions logged permanently in revision history.
- Editors work inside one assigned category, not platform-wide.
- Readers flag inaccuracies; enough upheld flags pull an article into editorial
  review and lower its score.
- Contributors monetise through per-contributor premium subscriptions on a tiered
  revenue share.

## Capabilities and Constraints

- Search is **rule-based keyword matching** against title, tags, and category. PDD
  Figure 5.7 states explicitly there is no semantic or predictive matching — the
  ranking must stay inspectable.
- Scoring thresholds are administrator-configurable at runtime (PRD §1.3.2), so no
  score constant may be hard-coded into the interface.
- Accuracy Rate is **withheld** until a contributor passes a minimum article count;
  until then the profile reads "New Contributor". A withheld rate is not a zero and
  must never render as one.
- Premium access is checked against a live subscription, never a role label.
- Responsive from 360px up; latest two versions of Chrome, Edge, Firefox, Safari.
- 95% of pages and searches under 3s; scores recalculated within 2s (PRD §5.1).

## Brand Commitments

The visual world is pinned by the client to the Medium design system
(styles.refero.design), rebased on **#133955** as the sole hue. Recorded in
DESIGN.md. Binding constraints carried from that reference: no chromatic colour in
UI, no shadows, typographic rather than coloured links.

## Evidence on Hand

- PRD (v1, 1 Aug 2026) and PDD (v1.0, 7 Aug 2026) — the PDD is authoritative where
  the two disagree.
- 50 seeded demo articles, six role accounts, and a working scoring engine.
- **No real user research, testimonials, press, partnerships, traffic figures, or
  named customers exist.** None may be fabricated in interface copy.
- The platform has never been deployed. No uptime, scale, or adoption claim is true.

## Product Principles

1. **Show the arithmetic.** A score without its breakdown is the hidden model this
   product exists to reject.
2. **Absence is not failure.** "New Contributor" is a legitimate state, not a bad
   one, and must never be styled as a warning.
3. **The human decides.** Scores prioritise editorial attention; they never
   auto-publish, auto-retract, or replace a human call.
4. **Permission is the server's word.** The interface hides what a role cannot do as
   a courtesy; Flask remains the authority.
5. **Content outranks interface.** Reading is the job. Chrome recedes.

## Accessibility & Inclusion

PRD §5.1 requires 80% of UAT participants to complete role-specific tasks unaided,
and no core function hidden or inaccessible at any width from 360px. Because the
committed palette is monochromatic, **no state may be signalled by colour alone** —
credibility bands, errors, and status all carry a text or shape encoding.
