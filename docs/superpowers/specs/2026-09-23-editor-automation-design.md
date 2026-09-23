# Editor automation

Design, 23 September 2026. Project FYP-26-S3-10, Wollongong News.

## The problem

Editors review every submission before it is published. When submissions
outpace review, articles sit in the queue for days and the platform stops
looking live. The request was for editors to be able to auto-approve under that
pressure.

Auto-approval on its own opens the attack the platform exists to close. A writer
publishes ten unremarkable but accurate articles, clears the trust threshold,
and then pushes one false story through unreviewed. Ten honest articles buy one
unchecked one, and a per-writer trust score is exactly what makes that worth
doing.

So the design treats throughput as three separate problems, and only the third
lets anything past a human.

1. Editor attention is allocated by arrival order rather than by risk.
2. Approving many low-risk articles costs one click each rather than one click.
3. Under genuine overload, some articles must publish without review.

Layers 1 and 2 are the bulk of the throughput gain and neither bypasses review.
Layer 3 bypasses it, and is off by default.

## Decisions taken

| Decision | Choice |
|---|---|
| Does the reader learn an article was not reviewed? | Yes. Visible label until an editor confirms. |
| Does auto-publish change the credibility score? | No. The label sits beside the number, not inside it. |
| Is auto-publish on by default? | No. An administrator turns it on. |
| Are premium articles eligible? | No. If a reader is paying, a human reads it first. |
| How long is eligibility suspended after a correction? | 90 days. |

The last two were my recommendations rather than explicit instructions. Both are
`PlatformSetting` rows, so changing either is a configuration change at runtime,
not a code change or a deploy.

## Constraint that shapes everything

`render.yaml` runs `gunicorn --workers 1`, because Flask-Limiter keeps its
counters in process memory. One worker serves every request. Nothing in this
design may do expensive work inside a request, so the backlog sweep is a
scheduled command rather than a request handler.

## Layer 1: order the review queue by risk

`review_queue()` in `modules/review.py` currently ends with

    query.order_by(Article.submitted_at.asc())

and then, for every pending article, calls `explain_article()` to compute the
credibility breakdown the article would carry on publication. That breakdown is
rendered and then discarded for ordering purposes. The signal already exists.

### New module: `app/triage.py`

A pure function, built to the same discipline as `credibility.py`: no database
access, no clock, no randomness, every constant tunable. Same reasons, and it
keeps the priority explainable to an editor who asks why an article is where it
is.

    review_priority(
        *,
        contributor_accuracy: float | None,   # None while the writer is new
        source_count: int,
        has_duplicate_title: bool,
        hours_waiting: float,
        settings: dict | None = None,
    ) -> PriorityBreakdown

Higher means a human is needed sooner.

| Signal | Contribution |
|---|---|
| Contributor has no accuracy rate yet | `new_contributor_weight` |
| Accuracy below the platform baseline | scales with the shortfall |
| Fewer sources than `expected_sources` | scales with the shortfall |
| Title matches an existing article | `duplicate_weight` |
| Time already spent waiting | `hours_waiting * wait_weight` |

`hours_waiting` is passed in rather than read from a clock, so the function
stays pure and testable. The caller supplies it.

The wait term is the anti-starvation guarantee. Without it a trusted writer's
article can sit at the bottom of a busy queue indefinitely. With it, everything
surfaces eventually regardless of how safe it looks.

`PriorityBreakdown` carries the per-signal contributions as well as the total,
so the queue can show an editor why an item is ranked where it is, the same way
`ScoreBreakdown` explains a credibility score.

### Wiring in the duplicate check

`duplicate_titles()` exists at `modules/moderation.py:259` and **nothing calls
it**. It is dead code today. Layer 1 is its first caller, and Layer 3 reuses it
as an eligibility gate.

Its current implementation is an exact normalised title match with no fuzzy
logic. That is a weak plagiarism check and is left as-is here; replacing it with
real body similarity is the separate plagiarism feature and plugs into the same
two call sites when it lands.

### Settings ownership

`modules/admin.py` imports `DEFAULTS` from `..credibility` and validates every
settings write against it, rejecting unknown keys. Adding triage constants to
`credibility.DEFAULTS` would put queue-ordering concerns inside the scoring
engine.

Instead `triage.py` exports its own `DEFAULTS`, and `admin.py` validates against
the union of the two. One import and one dict merge in `admin.py`; the scoring
engine is untouched.

## Layer 2: approve a batch in one click

    POST /review/batch-approve
    { "articleIds": [12, 18, 23, ...] }

The client sends the explicit list the editor saw on screen. The server does not
re-derive "everything below a risk threshold", because the set the editor looked
at and the set the server would compute can differ between render and click, and
the editor must approve only what they actually saw.

Reuses the existing `approve()` path rather than duplicating it, so
notifications, `rescore_article()` and audit entries behave identically to a
single approval.

Guards:

- `roles_required(*REVIEW_ROLES)`, the same decorator the single approve uses
- batch size capped
- each article re-checked as still `PENDING` and still inside the editor's
  assigned categories before it is touched
- **one `AuditLog` row per article, never one for the batch.** Thirty approvals
  are thirty decisions and the log must read that way

Partial failure returns which ids succeeded and which did not, rather than
failing the whole batch.

## Layer 3: publish under overload, and say so

### Schema

Two nullable columns on `Article`:

- `auto_published_at: datetime | None`
- `review_confirmed_at: datetime | None`

The status stays `PUBLISHED` throughout. A new `ArticleStatus.PROVISIONAL` was
considered and rejected: every query that filters on `status == PUBLISHED`
(discovery, feeds, search, category pages, scoring, the accuracy-rate counts in
`_published_counts`) would need updating, and missing one would silently drop an
article out of a feed. Two nullable columns change nothing that already works.

The label shows when `auto_published_at` is set and `review_confirmed_at` is
not. An editor confirming the article sets the second and the label clears.

One Alembic migration, both columns nullable, no backfill.

### The sweep

A fourth Flask CLI command in `app/cli.py`, alongside the existing `publish-due`
and `dispatch-notifications`:

    flask autopublish-backlog

Cron'd like the other two. No new infrastructure, and nothing expensive runs
inside a web request.

### Conditions

Every value a `PlatformSetting` row, owned by `triage.DEFAULTS`.

Pressure, at least one of:

- pending queue depth above `autopublish_queue_depth`
- oldest pending article older than `autopublish_max_wait_hours`

Article eligibility, all of:

- contributor accuracy at or above `autopublish_min_accuracy`
- contributor published count at or above `autopublish_min_articles`
- contributor not currently suspended from auto-publish
- at least one valid source tagged
- no duplicate-title match
- not a premium article

`autopublish_enabled` defaults to off.

### Revocation

When a correction is logged against an article whose `auto_published_at` is set,
that contributor is suspended from auto-publish for
`autopublish_suspension_days`, default 90.

This is what makes trust expensive to spend. The privilege is revocable and the
consequence lands immediately, so the build-trust-then-spend-it attack costs the
attacker their standing on the first use.

Every auto-publish writes an `AuditLog` row with the contributor, the article
and the pressure condition that opened the valve.

## What this deliberately does not touch

- **`credibility.py`.** The label is separate information displayed beside the
  score, never folded into it. The scoring engine stays a pure function of the
  inputs it has today, which keeps the published arithmetic checkable and means
  the 139 existing tests around it need no revision.
- **Existing status queries.** Nothing filtering on `PUBLISHED` changes.
- **The permission model.** New endpoints use the existing decorators from
  `security.py`. No new access logic.

## Interface surface

Backend:

- `app/triage.py`, new, pure, with its own `DEFAULTS`
- `modules/review.py`, queue ordering and the batch endpoint
- `modules/admin.py`, validate settings against the union of both `DEFAULTS`
- `modules/moderation.py`, suspension on correction
- `app/cli.py`, the sweep command
- one Alembic migration

Frontend:

- `pages/ReviewQueue.jsx`, risk ordering, why-ranked display, batch selection
- `components/Credibility.jsx`, the "Not yet reviewed" label
- article page and article cards, wherever the label must appear

The label is text, not colour. It follows the existing rule that no state on the
platform is signalled by colour alone.

## Testing

Added to the existing pytest suite, which must stay green at 139 plus the new
cases.

- `triage.review_priority` unit tests: each signal in isolation, a new
  contributor outranking a veteran on an otherwise identical article, and the
  wait term eventually lifting a safe article above a risky new one
- batch approve: partial failure, an article that left `PENDING` between render
  and click, an article outside the editor's categories, the per-article audit
  rows
- the sweep: below pressure nothing publishes, above pressure only eligible
  articles publish, premium excluded, suspended contributors excluded
- revocation: a correction on an auto-published article suspends the contributor
- labelling: set on auto-publish, cleared on confirmation

## Open

Nothing blocking. The two defaults chosen above (premium ineligible, 90-day
suspension) were recommendations rather than instructions, and both are runtime
settings if they turn out wrong.
