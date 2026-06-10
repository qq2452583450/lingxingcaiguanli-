from pathlib import Path


def test_requirements_include_openpyxl_for_excel_exports():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "openpyxl" in requirements
