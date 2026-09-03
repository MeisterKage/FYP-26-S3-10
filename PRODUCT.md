# Product

## Platform

web

## Stack

React (Vite) SPA, Flask REST API, PostgreSQL via Supabase. Committed in PDD 2.1
and 2.2; the database is a team decision recorded in the project README. Flask is
the single entry point, and no client ever queries the database directly.

## Users

Six tiers, from PDD 1 and PRD 1.3.2:

- **Unregistered visitor.** Reads public articles, browses categories, sees
  credibility scores. Cannot comment or publish.
- **Free registered reader.** Comments, likes, follows, saves reading lists, sets
  category interests, reports inaccuracies, applies to contribute.
- **Premium registered reader.** The above plus subscriber-only articles.
- **Verified contributor.** Drafts, submits, and schedules articles; tags
  verifiable sources; tracks their Accuracy Rate and earnings.
- **Editor.** Reviews and approves submissions within an assigned content
  category only, moderates flagged content, issues corrections.
- **System administrator.** Account governance, contributor applications,
  categories, platform-wide scoring thresholds, dispute resolution, logs.

The situation that matters is a reader deciding, in seconds, whether to trust an
article by someone they have never heard of.

## Product purpose

A news publishing platform where every article carries a **Credibility Score**
and every contributor an **Accuracy Rate**, both produced by a fixed, disclosed
formula rather than a hidden or predictive model. It works when a reader can
trace exactly why a score is what it is.

## Positioning

The disclosure is the differentiator. Competitors either hide their ranking
(algorithmic feeds) or have none (open publishing). PRD 1.3.3 and PDD 1 commit to
arithmetic a reader can follow: contributor accuracy, a fixed value per
verifiable source link, a fixed penalty per correction or retraction, and a
further penalty once reader reports pass an administrator-set threshold. Every
input is published, so a competing product cannot copy the claim without also
publishing its formula.

## Operating context

- Articles move draft, submitted, editor review, published, with corrections and
  retractions logged permanently in revision history.
- Editors work inside one assigned category rather than platform-wide.
- Readers flag inaccuracies. Enough upheld flags pull an article into editorial
  review and lower its score.
- Contributors earn through per-contributor premium subscriptions on a tiered
  revenue share.

## Capabilities and constraints

- Search is rule-based keyword matching against title, tags, and category. PDD
  Figure 5.7 states there is no semantic or predictive matching, because the
  ranking has to stay inspectable.
- Scoring thresholds are administrator-configurable at runtime (PRD 1.3.2), so no
  score constant may be hard-coded into the interface.
- Accuracy Rate is withheld until a contributor passes a minimum article count.
  Until then the profile reads "New Contributor". A withheld rate is not a zero
  and must never render as one.
- Premium access is checked against a live subscription, never a role label.
- Responsive from 360px up; latest two versions of Chrome, Edge, Firefox, Safari.
- 95% of pages and searches under 3s; scores recalculated within 2s (PRD 5.1).

## Brand commitments

The client pinned the visual world to the Medium design system
(styles.refero.design), rebased on **#133955** as the sole hue. DESIGN.md records
it. Three constraints carry over from that reference: no chromatic colour in UI,
no shadows, and typographic rather than coloured links.

## Evidence on hand

- PRD (v1, 1 Aug 2026) and PDD (v1.0, 7 Aug 2026). The PDD wins where the two
  disagree.
- 50 seeded demo articles, six role accounts, and a working scoring engine.
- No real user research, testimonials, press, partnerships, traffic figures, or
  named customers exist. None may be invented in interface copy.
- The platform has never been deployed, so no uptime, scale, or adoption claim is
  true.

## Product principles

1. Show the arithmetic. A score without its breakdown is the hidden model this
   product exists to reject.
2. A missing score is a legitimate state. "New Contributor" means no track record
   yet, and it must never be styled as a warning.
3. Scores prioritise editorial attention. They never auto-publish, auto-retract,
   or replace a human decision.
4. Flask is the authority on permission. The interface hides what a role cannot
   do as a courtesy, and that is all it does.
5. Reading is the job, so the interface stays out of the way of the content.

## Accessibility and inclusion

PRD 5.1 requires 80% of UAT participants to complete role-specific tasks unaided,
with no core function hidden or inaccessible at any width from 360px. Because the
committed palette is monochromatic, no state may be signalled by colour alone.
Credibility bands, errors, and status all carry a text or shape encoding.
