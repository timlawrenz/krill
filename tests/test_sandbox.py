"""Tests for the sandbox help parser."""

from krill.sandbox import parse_argparse_style, parse_click_style


SAMPLE_ARGPARSE = """usage: myprog [-h] [-f] [-o OUTPUT] [--verbose]

Do something useful.

optional arguments:
  -h, --help            show this help message and exit
  -f, --force           Force the operation
  -o OUTPUT, --output OUTPUT
                        Output file path
  --verbose             Enable verbose output
"""

SAMPLE_CLICK = """Usage: myprog [OPTIONS]

  Do something useful.

Options:
  -f, --force           Force the operation
  -o, --output TEXT     Output file path
  --verbose             Enable verbose output
  --help                Show this message and exit.
"""


def test_parse_argparse_style():
    result = parse_argparse_style(SAMPLE_ARGPARSE)
    assert result is not None
    assert len(result.options) == 4  # -h, -f, -o, --verbose

    force = [o for o in result.options if o["long"] == "--force"][0]
    assert force["short"] == "-f"
    assert force["type"] == "boolean"
    assert force["description"] == "Force the operation"

    output = [o for o in result.options if o["long"] == "--output"][0]
    assert output["type"] == "string"
    assert output["description"] == "Output file path"


def test_parse_click_style():
    result = parse_click_style(SAMPLE_CLICK)
    assert result is not None
    assert len(result.options) == 4  # including --help

    output = [o for o in result.options if o["long"] == "--output"][0]
    assert output["description"] == "Output file path"


def test_parse_empty():
    assert parse_argparse_style("no help here") is None
    assert parse_click_style("no help here") is None