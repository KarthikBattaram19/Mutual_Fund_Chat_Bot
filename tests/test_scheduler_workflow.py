import re
from pathlib import Path

import pytest


WORKFLOW_PATH = Path(".github/workflows/ingest_corpus.yml")
CRON_PATTERN = re.compile(r"^\s*-\s*cron:\s*['\"]?(.+?)['\"]?\s*$", re.MULTILINE)


def read_workflow() -> str:
    assert WORKFLOW_PATH.is_file(), f"Missing scheduler workflow: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def parse_cron_fields(cron_expr: str) -> list[str]:
    fields = cron_expr.strip().strip("'\"").split()
    if len(fields) != 5:
        raise ValueError(f"Expected 5 cron fields, got {len(fields)}: {cron_expr!r}")
    return fields


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return read_workflow()


def test_scheduler_workflow_file_exists() -> None:
    read_workflow()


def test_scheduler_workflow_has_daily_schedule_and_manual_dispatch(workflow_text: str) -> None:
    assert "schedule:" in workflow_text
    assert "workflow_dispatch:" in workflow_text

    match = CRON_PATTERN.search(workflow_text)
    assert match is not None, "Expected a cron schedule in the workflow"

    minute, hour, day_of_month, month, day_of_week = parse_cron_fields(match.group(1))
    assert minute == "0"
    assert hour == "5"  # 05:00 UTC = 10:30 AM IST
    assert day_of_month == "*"
    assert month == "*"
    assert day_of_week == "*"


def test_scheduler_workflow_invokes_ingest_corpus_cli(workflow_text: str) -> None:
    assert "python scripts/ingest_corpus.py" in workflow_text
    assert "--dry-run" not in workflow_text


def test_scheduler_workflow_installs_dependencies_and_playwright(workflow_text: str) -> None:
    assert "pip install -r requirements.txt" in workflow_text
    assert "playwright install" in workflow_text


def test_scheduler_workflow_uploads_expected_artifacts(workflow_text: str) -> None:
    assert "actions/upload-artifact@v4" in workflow_text
    for path in (
        "data/corpus_index.json",
        "data/vector_store/",
        "data/sample_chunks.json",
        "logs/ingestion_run.log",
    ):
        assert path in workflow_text


def test_scheduler_workflow_commits_refreshed_corpus_for_deploy(workflow_text: str) -> None:
    assert "permissions:" in workflow_text
    assert "contents: write" in workflow_text
    assert "Commit refreshed corpus for Railway rebuild" in workflow_text
    assert "git add data/corpus_index.json data/sample_chunks.json" in workflow_text
    assert "git push" in workflow_text


def test_scheduler_workflow_sets_vector_store_path(workflow_text: str) -> None:
    assert "VECTOR_STORE_PATH" in workflow_text
    assert "data/vector_store" in workflow_text


def test_scheduler_workflow_supports_self_hosted_runner_option(workflow_text: str) -> None:
    assert "self-hosted" in workflow_text
