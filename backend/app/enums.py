"""Shared enumerations.

Role tiers come from PDD Section 1: six tiers, stored as a single `role` field on
User so the permission model is enforceable against one table (PDD Section 4).

PREMIUM_REGISTERED is listed by the PDD as a tier, but premium access is really a
time-bounded entitlement. We therefore store the tier on the user AND derive live
premium access from an active Subscription row. See User.has_premium_access.
The role field alone must never be the paywall check, or a lapsed subscriber keeps
access forever.
"""
from enum import Enum


class Role(str, Enum):
    FREE_REGISTERED = "free_registered"
    PREMIUM_REGISTERED = "premium_registered"
    VERIFIED_CONTRIBUTOR = "verified_contributor"
    EDITOR = "editor"
    SYSTEM_ADMIN = "system_admin"

    #Unregistered is the absence of a session, never a stored row.


#: Tiers that may author articles.
AUTHORING_ROLES = frozenset({Role.VERIFIED_CONTRIBUTOR, Role.EDITOR, Role.SYSTEM_ADMIN})
#: Tiers that may act on the review queue.
REVIEW_ROLES = frozenset({Role.EDITOR, Role.SYSTEM_ADMIN})


class ArticleStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"        #submitted, awaiting editor review
    SCHEDULED = "scheduled"    #approved, publishes at published_at
    PUBLISHED = "published"
    REJECTED = "rejected"
    UNPUBLISHED = "unpublished"  #taken down by editor/admin
    RETRACTED = "retracted"


class DisputeStatus(str, Enum):
    OPEN = "open"
    UPHELD = "upheld"       #the correction stands
    REVERSED = "reversed"   #the correction is overturned and scores restored


class CorrectionType(str, Enum):
    CORRECTION = "correction"
    RETRACTION = "retraction"


class ReportStatus(str, Enum):
    OPEN = "open"
    UPHELD = "upheld"      #confirmed inaccurate -> feeds the score penalty
    DISMISSED = "dismissed"


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"   #active until period_end, then lapses
    EXPIRED = "expired"
