from collections.abc import Sequence

from sqlalchemy import Select, or_

from .database import Document

PERMISSION_NOTICE = (
    "TODO: production permissions are not enforced yet. Add Aternum scopeVisibleTo-style "
    "filtering before using this with private data."
)


def apply_search_filters(search_statement: Select, tag_filters: Sequence[str]) -> Select:
    filtered_statement = apply_tag_filters(search_statement, tag_filters)
    return apply_visibility_filters(filtered_statement)


def apply_tag_filters(search_statement: Select, tag_filters: Sequence[str]) -> Select:
    normalized_tag_filters = [tag_filter.strip() for tag_filter in tag_filters if tag_filter.strip()]
    if not normalized_tag_filters:
        return search_statement

    tag_match_clauses = [Document.tags.contains([tag_filter]) for tag_filter in normalized_tag_filters]
    return search_statement.where(or_(*tag_match_clauses))


def apply_visibility_filters(search_statement: Select) -> Select:
    # TODO: implement the production equivalent of Aternum Node::scopeVisibleTo(user):
    # 1. own nodes by user_id
    # 2. connected profile nodes with matching circle:* tags
    # 3. profile:* mention tags plus live connection checks
    # 4. circle membership catch-all across all profiles owned by the user
    return search_statement
