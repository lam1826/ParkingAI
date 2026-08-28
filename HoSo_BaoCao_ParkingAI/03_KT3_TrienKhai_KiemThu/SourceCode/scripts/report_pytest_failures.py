"""Emit failed JUnit test cases as GitHub Actions error annotations."""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


def _escape_workflow_value(value: str) -> str:
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def _source_path(classname: str) -> str:
    parts = [part for part in classname.split(".") if part]
    return "/".join(parts) + ".py" if parts else ".github"


def report_failures(junit_path: Path) -> int:
    root = ET.parse(junit_path).getroot()
    failures = 0
    for testcase in root.iter("testcase"):
        problem = testcase.find("failure")
        if problem is None:
            problem = testcase.find("error")
        if problem is None:
            continue

        failures += 1
        classname = testcase.get("classname", "")
        test_name = testcase.get("name", "unknown test")
        details = (problem.text or problem.get("message") or "pytest failure").strip()
        message = _escape_workflow_value(
            f"{classname}.{test_name}\n{details}"
        )
        path = _escape_workflow_value(_source_path(classname))
        print(f"::error file={path},title=pytest failure::{message}")

    if not failures:
        print("::error file=.github/workflows/ci.yml,title=pytest failure::"
              "pytest failed but JUnit contained no failed test cases")
        return 1

    print(f"Reported {failures} pytest failure(s) as GitHub annotations.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("junit_path", type=Path)
    args = parser.parse_args()
    return report_failures(args.junit_path)


if __name__ == "__main__":
    raise SystemExit(main())
