import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Requires Node.js")
def test_knowledge_graph_uses_explicit_versioned_relationships():
    result = subprocess.run(
        ["node", str(Path(__file__).parent / "node/knowledge_graph.cjs")],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
