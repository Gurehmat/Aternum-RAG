from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Select, and_, false, or_

from .database import Document

PERMISSION_NOTICE = (
    "Visibility filtering is enforced at the document level and mirrors Aternum "
    "Node::scopeVisibleTo. It requires a fully resolved ViewerPermissionContext supplied by "
    "the caller (ABE): owned profile ids, circle tags, and live connected profile "
    "ids. With an empty context it fails closed — the viewer sees only their own "
    "documents."
)


class ViewerPermissionContext(BaseModel):
    """Resolved viewer facts required by the PDF's scopeVisibleTo checks.

    The RAG service does NOT re-derive connections or circle membership — that
    logic and data live in ABE (relationships table, getUserCircleTags()). ABE
    already computes these on every feed request and passes them in, so this
    service stays a pure function of its inputs.
    """

    model_config = ConfigDict(frozen=True)

    user_id: UUID = Field(description="The authenticated Aternum user id.")
    owned_profile_ids: list[UUID] = Field(
        default_factory=list,
        description="All profile ids owned by the user, including curated profiles.",
    )
    circle_tags: list[str] = Field(
        default_factory=list,
        description="Resolved getUserCircleTags() output, e.g. circle:my_family:{profile_id}.",
    )
    connected_profile_ids: list[UUID] = Field(
        default_factory=list,
        description="Live connected author profile ids from the relationships table.",
    )

    @field_validator("circle_tags")
    @classmethod
    def validate_circle_tags(cls, circle_tags: Sequence[str]) -> list[str]:
        normalized_circle_tags = unique_normalized_values(circle_tags)
        invalid_circle_tags = [tag_name for tag_name in normalized_circle_tags if not tag_name.startswith("circle:")]
        if invalid_circle_tags:
            raise ValueError(f"circle_tags must contain only circle:* tags: {invalid_circle_tags}")
        return normalized_circle_tags

    @property
    def user_id_value(self) -> str:
        return str(self.user_id)

    @property
    def owned_profile_id_values(self) -> list[str]:
        return [str(profile_id) for profile_id in self.owned_profile_ids]

    @property
    def connected_profile_id_values(self) -> list[str]:
        return [str(profile_id) for profile_id in self.connected_profile_ids]


def apply_search_filters(
    search_statement: Select,
    tag_filters: Sequence[str],
    viewer: ViewerPermissionContext,
) -> Select:
    """Apply visibility (security gate) then optional tag/tab filters.

    Order matters and is deliberate: visibility is AND-ed with the tag filters,
    exactly like scopeVisibleTo() runs before applyFeedFilters(). Tag filters
    only narrow WITHIN what the viewer is already allowed to see; they can never
    widen visibility, because every clause is a chained .where() (logical AND).
    """
    visible_statement = apply_visibility_filters(search_statement, viewer)
    return apply_tag_filters(visible_statement, tag_filters)


def apply_tag_filters(search_statement: Select, tag_filters: Sequence[str]) -> Select:
    """Optional 'which tab am I viewing' narrowing. Matches any of the given tags."""
    normalized_tag_filters = [tag_filter.strip() for tag_filter in tag_filters if tag_filter.strip()]
    if not normalized_tag_filters:
        return search_statement

    tag_match_clauses = [Document.tags.contains([tag_filter]) for tag_filter in normalized_tag_filters]
    return search_statement.where(or_(*tag_match_clauses))


def apply_visibility_filters(search_statement: Select, viewer: ViewerPermissionContext) -> Select:
    """Production equivalent of Aternum Node::scopeVisibleTo(user).

    Four checks combined with OR — a document is visible if ANY passes:
      1. Own nodes (user_id == viewer).
      2. Connected author + matching circle tag.
      3. @mention tag (profile:*) AND author is still a live connection.
      4. Circle membership catch-all across all circle tags the viewer holds.

    A document with no circle tags ("Only Me") can only pass check 1 — it cannot
    match the circle overlap (4) or the mention clause (3) — which preserves the
    private-by-default rule with no special casing.
    """
    # Check 1 — own content. Always visible.
    visibility_clauses = [Document.user_id == viewer.user_id_value]

    # Check 2 — connected author's content with a matching circle tag.
    if viewer.connected_profile_ids and viewer.circle_tags:
        visibility_clauses.append(
            and_(
                Document.profile_id.in_(viewer.connected_profile_id_values),
                document_has_any_tag(viewer.circle_tags),
            )
        )

    # Check 3 — @mention AND live connection. The connection half is what makes a
    # permanent mention tag follow the LIVE relationship: the profile:* tag
    # persists in the DB after a disconnect, but visibility drops because the
    # author is no longer in connected_profile_ids.
    if viewer.owned_profile_ids and viewer.connected_profile_ids:
        mention_tags = [f"profile:{profile_id}" for profile_id in viewer.owned_profile_id_values]
        visibility_clauses.append(
            and_(
                Document.profile_id.in_(viewer.connected_profile_id_values),
                document_has_any_tag(mention_tags),
            )
        )

    # Check 4 — circle membership catch-all. This is intentionally broader than
    # Check 2, matching the PDF: it does not require a direct connection.
    if viewer.circle_tags:
        visibility_clauses.append(document_has_any_tag(viewer.circle_tags))

    return search_statement.where(or_(*visibility_clauses))


def document_has_any_tag(tag_names: Sequence[str]):
    """Sandbox tag adapter.

    The PDF's real model is tags + taggables with tag type checks. This prototype
    stores tag names as JSON on Document, so each tag check becomes JSONB
    contains([tag]). When the real DB is available, replace only this helper with
    the proper tags/taggables join while keeping the four visibility checks above.
    """
    normalized_tag_names = unique_normalized_values(tag_names)
    if not normalized_tag_names:
        return false()
    return or_(*[Document.tags.contains([tag_name]) for tag_name in normalized_tag_names])


def unique_normalized_values(values: Sequence[str]) -> list[str]:
    normalized_values = [str(value).strip() for value in values if str(value).strip()]
    return list(dict.fromkeys(normalized_values))
