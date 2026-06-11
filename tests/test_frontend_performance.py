from pathlib import Path


def _function_body(source, name):
    marker = f"function {name}("
    async_marker = f"async function {name}("
    if marker in source:
        start = source.index(marker)
    else:
        start = source.index(async_marker)
    brace_start = source.index("{", start)
    depth = 0
    for pos in range(brace_start, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start + 1:pos]
    raise AssertionError(f"Function {name} body not found")


def test_selection_inquiry_renders_before_background_data_loading():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    body = _function_body(source, "openInquiryWithItems")

    show_modal_pos = body.index("modal.classList.add('show');")
    immediate_build_pos = body.index("_buildItems();", show_modal_pos)
    background_load_pos = body.index("Promise.all([")

    assert immediate_build_pos < background_load_pos


def test_edit_inquiry_opens_modal_before_heavy_material_cache_loading():
    source = Path("static/js/app.js").read_text(encoding="utf-8")
    body = _function_body(source, "editInquiry")

    show_modal_pos = body.index("modal.classList.add('show');")
    material_load_pos = body.index("loadAllMaterialsForSelect")

    assert show_modal_pos < material_load_pos
