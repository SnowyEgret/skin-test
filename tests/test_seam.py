"""The module seam: what the student-house imports, and what it leaves behind.

`rules.py` and `pipeline.py` are the two modules that migrate. `build.py` is this
rig — the transcribed `PART_N` substrate, the OBJ emission, the printed report —
and it stays here. The split is only worth anything if the direction of the
dependency holds, and that is not something the build or the suite would
otherwise notice: an `import build` added to `rules.py` for one constant would
pass every other test in this repo and be discovered on the far side of the
migration, where the fix is expensive.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _imports(module: str) -> set[str]:
    """The top-level package names `module` imports, however it spells them."""
    tree = ast.parse((ROOT / f"{module}.py").read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("module", ["rules", "pipeline"])
def test_a_migrating_module_never_imports_the_rig(module):
    """Neither may reach back into `build.py`, at module level or inside a function.

    `ast` rather than an import of the module itself, because a deferred import
    inside a function body is exactly the one that would slip through: it never
    runs in the suite and never runs in the build, and it would still have to be
    unpicked on migration.
    """
    assert "build" not in _imports(module), (
        f"{module}.py imports the rig — the two modules that migrate cannot depend "
        f"on the substrate transcription, the OBJ emission or the printed report"
    )


def test_the_geometry_core_knows_none_of_them():
    """`skin/` never learns what a wall or a membrane is — the oldest invariant here.

    Stated in CLAUDE.md as a rule about *knowledge*, which nothing can check; this
    is the mechanical half of it, which is that the dependency only ever points
    one way. It is what lets `skin/` migrate untouched.
    """
    for path in sorted((ROOT / "skin").glob("*.py")):
        tree = ast.parse(path.read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module.split(".")[0])
        stray = names & {"build", "rules", "pipeline", "audit"}
        assert not stray, f"skin/{path.name} imports {sorted(stray)}"


def test_the_seam_takes_a_dict_and_refuses_anything_else():
    """`run` is handed plain data — never a path, and never `None` to be filled in.

    The refusal is the point: `skins()` would quietly resolve a `None` against the
    committed file and hand back specs, and the failure would then surface as a
    `TypeError` inside `classifier` naming nothing. On migration that `None` is a
    missing `topo["skin"]`, and it has to say so.
    """
    import pipeline

    for bad in (None, "skin-parameters.yaml", 0.085):
        with pytest.raises(TypeError, match="validated parameter dict"):
            pipeline.run([], bad)
