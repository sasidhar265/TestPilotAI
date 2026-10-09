"""Local Tree-sitter parsing for generated automation source files."""

from collections.abc import Iterator
from functools import lru_cache

import tree_sitter_c_sharp
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_ruby
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

_GRAMMARS = {
    ".cs": tree_sitter_c_sharp.language,
    ".java": tree_sitter_java.language,
    ".js": tree_sitter_javascript.language,
    ".ts": tree_sitter_typescript.language_typescript,
    ".rb": tree_sitter_ruby.language,
}

_REGISTRATION_FIELDS = {
    "attribute": "name",
    "annotation": "name",
    "marker_annotation": "name",
    "call_expression": "function",
    "invocation_expression": "function",
    "call": "method",
}
_STEP_NAMES = frozenset(
    {"Given", "When", "Then", "GivenAttribute", "WhenAttribute", "ThenAttribute"}
)

BRANCH_NODES = frozenset(
    {
        "if_statement",
        "switch_statement",
        "switch_expression",
        "conditional_expression",
        "ternary_expression",
        "if",
        "if_modifier",
        "unless",
        "unless_modifier",
        "elsif",
        "case",
        "case_match",
        "conditional",
    }
)


@lru_cache(maxsize=len(_GRAMMARS))
def _language(suffix: str) -> Language:
    return Language(_GRAMMARS[suffix]())


def parse_source(suffix: str, source: str) -> Node | None:
    """Use a fresh parser per call; language definitions are safe to share."""
    if suffix not in _GRAMMARS:
        return None
    return Parser(_language(suffix)).parse(source.encode("utf-8")).root_node


def walk_nodes(root: Node) -> Iterator[Node]:
    """Visit nodes in source order without recursive Python calls."""
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.children))


def is_step_registration(node: Node) -> bool:
    field = _REGISTRATION_FIELDS.get(node.type)
    name = node.child_by_field_name(field) if field else None
    if name is None or name.text is None:
        return False
    value = name.text.decode("utf-8").rsplit(".", 1)[-1].strip().lstrip("@")
    return value in _STEP_NAMES
