import re
from pathlib import Path


def test_each_nav_module_has_matching_page_container():
    html = Path("index.html").read_text(encoding="utf-8")
    modules = set(re.findall(r'data-module="([^"]+)"', html))

    missing = [
        module for module in sorted(modules)
        if f'id="{module}Module"' not in html
    ]

    assert missing == []
