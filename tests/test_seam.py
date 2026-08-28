"""The module seam: what the student-house imports, and what it leaves behind.

`skinning` is the importable half — `skinning.rules` and `skinning.pipeline` over
`skinning.skin`. `build.py` and `audit.py` are this rig, they sit outside the
package, and they stay here. The split is only worth anything if the direction of
the dependency holds, and that is not something the build or the suite would
otherwise notice: an `import build` added to `skinning/rules.py` for one constant
would pass every other test in this repo and be discovered on the far side of the
migration, where the fix is expensive.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "skinning"
RIG = {"build", "audit"}


def _imports(path: Path) -> set[str]:
    """What `path` imports, with relative imports resolved against the package.

    An absolute import contributes its top-level package name; a relative one
    contributes the dotted path it resolves to *within* `skinning`, so
    `from ..rules import CORNICE` in `skinning/skin/offset.py` comes back as
    `"rules"`.

    Resolving them is the whole point, and skipping them was a real hole: in the
    flat layout the violation this file exists to catch was spelled
    `from rules import ...`, level 0, and was caught. Inside the package the same
    violation is `from ..rules import ...`, level 2 — and a helper that dropped
    every relative import let it through in silence, on the one test written to
    prevent it. Found on review, 2026-08-28.
    """
    tree = ast.parse(path.read_text())
    here = path.relative_to(PACKAGE).parent.parts
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    names.add(node.module.split(".")[0])
                continue
            # one level means "this package", so `level - 1` steps come off `here`
            base = list(here[: len(here) - (node.level - 1)])
            target = base + (node.module.split(".") if node.module else [])
            if target:
                names.add(".".join(target))
    return names


def _escapes(path: Path) -> bool:
    """Does this module compute a directory *above* its own?

    Read off the AST rather than by scanning the text, which is what this did
    first and which was wrong in both directions: the files here are prose-heavy,
    so a docstring mentioning `parent.parent` failed the suite with no defect,
    while a real second escape spelled `os.path.dirname(os.path.dirname(...))` or
    a `sys.path` insert went unseen. Found on review, 2026-08-28.

    `.parent` once is not an escape — that is the module's own directory, which is
    how `SCHEMA_PATH` reaches the schema beside it.
    """
    def dirname(func):
        return isinstance(func, ast.Attribute) and func.attr == "dirname"

    for node in ast.walk(ast.parse(path.read_text())):
        # `.parents[n]`, n >= 2 — `parents[0]` and `[1]` stay inside the package
        if (isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute) and node.value.attr == "parents"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, int) and node.slice.value >= 2):
            return True
        # `.parent.parent`
        if (isinstance(node, ast.Attribute) and node.attr == "parent"
                and isinstance(node.value, ast.Attribute) and node.value.attr == "parent"):
            return True
        # `os.path.dirname(os.path.dirname(...))`
        if isinstance(node, ast.Call) and dirname(node.func):
            if any(isinstance(a, ast.Call) and dirname(a.func) for a in node.args):
                return True
        # anything reaching for `sys.path`
        if (isinstance(node, ast.Attribute) and node.attr == "path"
                and isinstance(node.value, ast.Name) and node.value.id == "sys"):
            return True
    return False


@pytest.mark.parametrize("module", ["rules", "pipeline"])
def test_a_migrating_module_never_imports_the_rig(module):
    """Neither may reach back into `build.py`, at module level or inside a function.

    `ast` rather than an import of the module itself, because a deferred import
    inside a function body is exactly the one that would slip through: it never
    runs in the suite and never runs in the build, and it would still have to be
    unpicked on migration.
    """
    stray = _imports(PACKAGE / f"{module}.py") & RIG
    assert not stray, (
        f"skinning/{module}.py imports {sorted(stray)} — the package cannot depend "
        f"on the substrate transcription, the OBJ emission or the printed report"
    )


def test_the_geometry_core_knows_neither_the_rules_nor_the_rig():
    """`skinning/skin/` never learns what a wall or a membrane is — the oldest invariant here.

    Stated in CLAUDE.md as a rule about *knowledge*, which nothing can check; this
    is the mechanical half of it, which is that the dependency only ever points one
    way. It is what lets the geometry migrate untouched.
    """
    for path in sorted((PACKAGE / "skin").glob("*.py")):
        names = _imports(path)
        stray = sorted(
            n for n in names
            if n in RIG or n == "skinning" or n.split(".")[0] in {"rules", "pipeline"}
        )
        assert not stray, f"skinning/skin/{path.name} imports {stray}"


def test_the_package_reaches_outside_itself_in_exactly_one_place():
    """`parameters.py` resolves this repo's root to default its path, and nothing else does.

    It is the module CLAUDE.md says is deleted rather than ported on migration, and
    that reach is why. A second one appearing is worth failing over: an installed
    copy of this package has no repo root, so anything else computing one is reading
    a file that will not be there.
    """
    escapes = [
        path.relative_to(ROOT) for path in sorted(PACKAGE.rglob("*.py")) if _escapes(path)
    ]
    assert escapes == [Path("skinning/skin/parameters.py")], escapes


def test_the_seam_takes_a_dict_and_refuses_anything_else():
    """`run` is handed plain data — never a path, and never `None` to be filled in.

    The refusal is the point: `skins()` would quietly resolve a `None` against the
    committed file and hand back specs, and the failure would then surface as a
    `TypeError` inside `classifier` naming nothing. On migration that `None` is a
    missing `topo["skin"]`, and it has to say so.
    """
    from skinning import pipeline

    for bad in (None, "skin-parameters.yaml", 0.085):
        with pytest.raises(TypeError, match="validated parameter dict"):
            pipeline.run([], bad)
