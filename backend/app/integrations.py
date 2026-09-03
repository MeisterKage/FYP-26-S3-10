"""The three external services in PDD Section 2.1, stubbed behind interfaces.

v1 ships the interfaces and logs what *would* have happened. An examiner can see the call site
and the recorded intent, and swapping in a real provider later replaces one
class rather than forcing a refactor.

Do not inline calls to a real provider at the call sites. Everything goes through
these objects so the seam stays visible in the component diagram.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Email delivery
# --------------------------------------------------------------------------- #

class EmailDeliveryService:
    """PRD 5.1: notifications queued for delivery within 60 seconds of the trigger."""

    def send(self, *, to: str, subject: str, body: str) -> bool:
        log.info("[email:stub] to=%s subject=%r", to, subject)
        return True


# --------------------------------------------------------------------------- #
#  Payment gateway
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ChargeResult:
    ok: bool
    reference: str
    message: str = ""


#: Platform cut shrinks as a contributor's subscriber base grows (PRD 1.4.5).
REVENUE_TIERS: tuple[tuple[int, str, float], ...] = (
    (0, "tier_1", 0.30),
    (100, "tier_2", 0.20),
    (1000, "tier_3", 0.10),
)


def revenue_tier_for(subscriber_count: int) -> tuple[str, float]:
    """Return (tier_name, platform_share) for a subscriber count."""
    name, share = REVENUE_TIERS[0][1], REVENUE_TIERS[0][2]
    for threshold, tier_name, tier_share in REVENUE_TIERS:
        if subscriber_count >= threshold:
            name, share = tier_name, tier_share
    return name, share


class PaymentGateway:
    def charge(self, *, user_id: int, amount_cents: int, description: str) -> ChargeResult:
        ref = f"stub_{user_id}_{int(datetime.now(timezone.utc).timestamp())}"
        log.info("[payment:stub] charge user=%s amount=%s %r", user_id, amount_cents, description)
        return ChargeResult(ok=True, reference=ref)

    def payout(self, *, contributor_id: int, amount_cents: int) -> ChargeResult:
        ref = f"stub_payout_{contributor_id}_{int(datetime.now(timezone.utc).timestamp())}"
        log.info("[payment:stub] payout contributor=%s amount=%s", contributor_id, amount_cents)
        return ChargeResult(ok=True, reference=ref)


# --------------------------------------------------------------------------- #
#  Social share
# --------------------------------------------------------------------------- #

class SocialShareService:
    """Builds the preview card carrying headline and credibility score (PDD Fig 5.8).

    Share URLs are real and need no API key or stub: each platform accepts a
    plain GET. Only the preview metadata is our responsibility.
    """

    def share_urls(self, *, article_url: str, title: str, score: float) -> dict[str, str]:
        text = quote(f"{title} — Credibility Score {score:.0f}/100")
        url = quote(article_url, safe="")
        return {
            "facebook": f"https://www.facebook.com/sharer/sharer.php?u={url}",
            "x": f"https://twitter.com/intent/tweet?url={url}&text={text}",
            "whatsapp": f"https://wa.me/?text={text}%20{url}",
            "telegram": f"https://t.me/share/url?url={url}&text={text}",
        }

    def preview_card(self, *, title: str, summary: str, score: float, band: str) -> dict:
        return {
            "og:title": title,
            "og:description": summary,
            "credibility:score": score,
            "credibility:band": band,
        }


email_service = EmailDeliveryService()
payment_gateway = PaymentGateway()
social_share = SocialShareService()
