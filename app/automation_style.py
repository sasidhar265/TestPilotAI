"""Static guardrails for thin step-definition adapters."""

import ast
import re
from pathlib import PurePosixPath

from app.code_syntax import BRANCH_NODES, is_step_registration, parse_source, walk_nodes

_NON_CODE = re.compile(
    r'@"(?:""|[^"])*"|"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\''
    r'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`'
    r"|//[^\n]*|/\*[\s\S]*?\*/"
)


def step_style_findings(path: str, source: str, *, detailed_diagnostics: bool = True) -> list[str]:
    suffix = PurePosixPath(path).suffix
    root = parse_source(suffix, source)
    if root is not None:
        nodes = list(walk_nodes(root))
        if not path.startswith("StepDefinitions/") and not any(
            is_step_registration(node) for node in nodes
        ):
            return []
        findings = []
        if root.has_error:
            error = next(node for node in nodes if node.is_error or node.is_missing)
            findings.append(
                f"{path}:{error.start_point.row + 1}:{error.start_point.column + 1}: "
                "invalid step-definition syntax; fix parsing errors before accepting the pack"
            )
        for node in nodes:
            if node.is_named and node.type in BRANCH_NODES:
                findings.append(
                    f"{path}:{node.start_point.row + 1}:{node.start_point.column + 1}: "
                    "step definitions must delegate conditional behavior to strategies/services; "
                    "if/else, switch/match and ternary expressions are not allowed "
                    f"({node.type})"
                )
        if findings and not detailed_diagnostics:
            return [
                f"{path}: step definitions must have valid syntax and delegate conditional "
                "behavior to strategies/services; if/else, switch/match and ternary expressions "
                "are not allowed"
            ]
        return findings
    registrations = re.search(
        r"(?:\[\s*(?:Given|When|Then)(?:Attribute)?\s*\("
        r"|@(?:given|when|then|Given|When|Then)\s*\("
        r"|\b(?:Given|When|Then)\s*\()",
        _NON_CODE.sub(lambda match: " " * len(match.group()), source),
    )
    if not path.startswith("StepDefinitions/") and not registrations:
        return []
    if suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return [f"{path}: invalid Python step definitions"]
        branches = any(isinstance(node, (ast.If, ast.IfExp, ast.Match)) for node in ast.walk(tree))
    else:
        code = _NON_CODE.sub(lambda match: " " * len(match.group()), source)
        if suffix == ".rb":
            code = re.sub(r"#[^\n]*", "", code)
        branches = bool(
            re.search(r"\b(?:if|else|switch|case|unless|elsif)\b", code)
            or re.search(r"(?<!\?)\?(?![?.])[^;{}]*:", code)
        )
    return (
        [
            f"{path}: step definitions must delegate conditional behavior to strategies/services; "
            "if/else, switch/match and ternary expressions are not allowed"
        ]
        if branches
        else []
    )
