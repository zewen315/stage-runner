"""Direct unit tests for load_workflow (lib/workflow_loader.py) -- every
other suite that loads a real workflow package only exercises its happy
path; its error paths (a package with no registry, or the wrong type)
were never covered on their own.

Each test builds its own throwaway package under a distinct name --
load_workflow adds the package to sys.modules by that name, so reusing a
name across tests would silently return a stale cached module instead of
re-loading the new one.
"""

import pytest

from stages import StageRegistry
from workflow_loader import load_workflow


def _make_package(tmp_path, name, init_contents):
    package_dir = tmp_path / name
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text(init_contents)
    return package_dir


def test_loads_the_registry_exposed_by_init(tmp_path):
    package_dir = _make_package(
        tmp_path,
        "wl_ok",
        "from stages import StageRegistry\nregistry = StageRegistry()\n",
    )

    registry = load_workflow(package_dir)

    assert isinstance(registry, StageRegistry)


def test_missing_registry_attribute_raises(tmp_path):
    package_dir = _make_package(tmp_path, "wl_missing", "")

    with pytest.raises(ValueError, match="no `registry"):
        load_workflow(package_dir)


def test_registry_of_wrong_type_raises(tmp_path):
    package_dir = _make_package(tmp_path, "wl_wrong_type", "registry = 'not a StageRegistry'\n")

    with pytest.raises(ValueError, match="no `registry"):
        load_workflow(package_dir)


def test_relative_imports_between_stage_files_work(tmp_path):
    """The whole point of loading it as a real package rather than
    exec()-ing a file: sibling modules can `from .registry import
    registry` to share one instance."""
    package_dir = _make_package(
        tmp_path,
        "wl_relative",
        "from .registry import registry\nfrom . import a\n",
    )
    (package_dir / "registry.py").write_text("from stages import StageRegistry\nregistry = StageRegistry()\n")
    (package_dir / "a.py").write_text(
        "from .registry import registry\n\n@registry.stage('a')\ndef a():\n    return 1\n"
    )

    registry = load_workflow(package_dir)

    assert [s.name for s in registry.all()] == ["a"]
