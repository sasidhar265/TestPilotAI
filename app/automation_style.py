"""Static guardrails for thin step-definition adapters."""

import ast
import re
from pathlib import PurePosixPath

_NON_CODE = re.compile(
    r'@"(?:""|[^"])*"|"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\''
    r'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`'
    r"|//[^\n]*|/\*[\s\S]*?\*/"
)


def step_style_findings(path: str, source: str) -> list[str]:
    registrations = re.search(
        r"(?:\[\s*(?:Given|When|Then)(?:Attribute)?\s*\("
        r"|@(?:given|when|then|Given|When|Then)\s*\("
        r"|\b(?:Given|When|Then)\s*\()",
        _NON_CODE.sub(lambda match: " " * len(match.group()), source),
    )
    if not path.startswith("StepDefinitions/") and not registrations:
        return []
    suffix = PurePosixPath(path).suffix
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
