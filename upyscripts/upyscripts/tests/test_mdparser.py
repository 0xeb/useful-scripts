from upyscripts.lib.markdown.heading_parser import parse_markdown


def test_parse_markdown_builds_nested_heading_tree():
    headings, parsed = parse_markdown(
        """# Meta

## YouTube

### URL

https://example.test/video

### Title

Example title
"""
    )

    assert [heading.title for heading in headings] == ["Meta"]
    assert parsed["Meta"]["YouTube"]["URL"]["contents"] == [
        "",
        "https://example.test/video",
        "",
    ]
    assert parsed["Meta"]["YouTube"]["Title"]["contents"] == [
        "",
        "Example title",
        "",
    ]


def test_markdown_dict_get_val_supports_nested_paths():
    _, parsed = parse_markdown("# Root\n## Child\nvalue")

    assert parsed.get_val("Root.Child") == "value"
    assert parsed.get_val("Root.Missing", "fallback") == "fallback"
