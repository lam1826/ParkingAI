from pathlib import Path

from scripts.report_pytest_failures import (
    _escape_workflow_value,
    _source_path,
    report_failures,
)


def test_ci_annotation_helpers_map_pytest_case_to_safe_workflow_values():
    assert _source_path("tests.test_example") == "tests/test_example.py"
    assert _escape_workflow_value("line 1\n100%") == "line 1%0A100%25"


def test_ci_annotation_reporter_emits_failure_and_fails_gate(
    tmp_path: Path, capsys
):
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        """<?xml version="1.0"?>
        <testsuites><testsuite tests="1" failures="1">
          <testcase classname="tests.test_example" name="test_linux_contract">
            <failure>expected true\nactual false</failure>
          </testcase>
        </testsuite></testsuites>
        """,
        encoding="utf-8",
    )

    assert report_failures(junit) == 1
    output = capsys.readouterr().out
    assert "file=tests/test_example.py" in output
    assert "test_linux_contract%0Aexpected true%0Aactual false" in output
