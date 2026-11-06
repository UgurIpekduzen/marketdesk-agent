"""Tests for the comparison of vector stores: the data, the command that starts
a measurement, how a worker's answer is read and summed up, and what the report
says. The stores themselves are not started: the measurement needs the
network and a clean environment for each, so it is run with `task
vector:compare` and not here."""

import json
import subprocess

import pytest

from eval import vector_store_compare as compare


def test_synthetic_vectors_are_the_same_for_the_same_seed():
    first = compare.synthetic_vectors(5, 8, seed=3)
    second = compare.synthetic_vectors(5, 8, seed=3)
    other = compare.synthetic_vectors(5, 8, seed=4)

    assert first == second
    assert first != other


def test_synthetic_vectors_have_unit_length_and_the_asked_shape():
    vectors = compare.synthetic_vectors(4, 16, seed=0)

    assert len(vectors) == 4
    assert all(len(vector) == 16 for vector in vectors)
    for vector in vectors:
        assert sum(value * value for value in vector) == pytest.approx(1.0)


def test_categories_alternate():
    assert [compare.category_of(index) for index in range(4)] == ["a", "b", "a", "b"]


def test_filter_holds_only_when_every_item_is_category_a():
    assert compare.filter_holds(["n0", "n2", "n10"]) is True
    assert compare.filter_holds(["n0", "n3"]) is False
    assert compare.filter_holds([]) is False


def test_command_builds_a_clean_environment_with_every_package():
    candidate = compare.Candidate("x", ["a==1", "b==2"], True)

    command = compare.uv_command(candidate, cold=False, arguments=["script.py"])

    assert command[:3] == ["uv", "run", "--isolated"]
    assert "--no-project" in command
    assert command[command.index("--python") + 1] == compare.PYTHON
    withs = [command[i + 1] for i, word in enumerate(command) if word == "--with"]
    assert withs == ["a==1", "b==2"]
    assert "--no-cache" not in command
    assert command[-3:] == ["python", "-I", "script.py"]


def test_command_ignores_the_cache_only_when_cold():
    candidate = compare.Candidate("x", ["a==1"], True)

    cold = compare.uv_command(candidate, cold=True, arguments=[])
    warm = compare.uv_command(candidate, cold=False, arguments=[])

    assert "--no-cache" in cold
    assert "--no-cache" not in warm


def test_parse_result_takes_the_last_marked_line_and_skips_noise():
    output = "\n".join(
        [
            "Installed 5 packages",
            compare.RESULT_MARK + json.dumps({"x": 1}),
            "a warning",
            compare.RESULT_MARK + json.dumps({"x": 2}),
            "trailing text",
        ]
    )

    assert compare.parse_result(output) == {"x": 2}


def test_parse_result_is_none_without_a_marked_line():
    assert compare.parse_result("only noise\nmore noise") is None


def test_spread_gives_the_median_and_the_range():
    assert compare.spread([3.0, 1.0, 2.0]) == {"median": 2.0, "min": 1.0, "max": 3.0}


def test_aggregate_leaves_failed_runs_out_and_counts_them():
    runs = [
        {"search_ms_p50": 1.0, "filter": "works"},
        {"error": "boom"},
        {"search_ms_p50": 3.0, "filter": "works"},
    ]

    summary = compare.aggregate(runs, ["search_ms_p50"])

    assert summary["search_ms_p50"] == {"median": 2.0, "min": 1.0, "max": 3.0}
    assert summary["failed_runs"] == 1
    assert summary["filter"] == "works"


def test_aggregate_reports_the_error_when_every_run_failed():
    summary = compare.aggregate([{"error": "no network"}, {"error": "x"}], ["a"])

    assert summary == {"error": "no network"}


def test_cell_shows_the_range_only_when_the_runs_differ():
    same = {"median": 2.0, "min": 2.0, "max": 2.0}
    different = {"median": 2.0, "min": 1.0, "max": 3.0}

    assert compare.cell(same) == "2.0"
    assert compare.cell(different) == "2.0 (1.0–3.0)"
    assert compare.cell(different, 0) == "2 (1–3)"


def test_cell_shows_no_range_when_the_rounded_figures_are_the_same():
    close = {"median": 0.1, "min": 0.12, "max": 0.14}

    assert compare.cell(close) == "0.1"


def test_every_candidate_has_a_worker_and_its_versions_are_pinned():
    for candidate in compare.CANDIDATES:
        assert compare.worker_key(candidate) in compare.WORKERS
        for package in candidate.packages:
            assert "==" in package


def test_only_the_candidates_on_llama_index_share_its_core():
    for candidate in compare.CANDIDATES:
        assert (compare.CORE in candidate.packages) is candidate.with_core


def failing_of_worker_failure_is_returned_as_an_error(command, **kwargs):
    return subprocess.CompletedProcess(command, 2, stdout="", stderr="a\nb\nc\nd")


def test_worker_failure_is_returned_as_an_error(monkeypatch):

    monkeypatch.setattr(
        compare.subprocess, "run", failing_of_worker_failure_is_returned_as_an_error
    )

    result = compare.run_worker(compare.CANDIDATES[1], [])

    assert result == {"error": "b c d"}


def answering_of_worker_answer_is_read_from_its_output(command, **kwargs):
    out = "noise\n" + compare.RESULT_MARK + json.dumps({"packages": 9})
    return subprocess.CompletedProcess(command, 0, stdout=out, stderr="")


def test_worker_answer_is_read_from_its_output(monkeypatch):

    monkeypatch.setattr(
        compare.subprocess, "run", answering_of_worker_answer_is_read_from_its_output
    )

    assert compare.run_worker(compare.CANDIDATES[1], []) == {"packages": 9}


def worker_answer(packages: int, disk_mb: float) -> dict:
    return {
        "packages": packages,
        "disk_mb": disk_mb,
        "peak_memory_mb": 100.0,
        "search_ms_p50": 1.0,
        "build_ms": 5.0,
        "filter": "works",
    }


def test_extra_figures_are_taken_from_the_core_when_the_store_runs_on_it(monkeypatch):
    monkeypatch.setattr(compare, "seconds_to_build", lambda candidate, cold: 2.0)
    monkeypatch.setattr(
        compare, "run_worker", lambda candidate, args: worker_answer(65, 250.0)
    )
    base = {"packages": 62, "disk_mb": 176.0}
    candidate = compare.Candidate("store", [compare.CORE, "x==1"], True)

    row = compare.measure_store(candidate, runs=2, base=base)

    assert row["extra_packages"] == 3
    assert row["extra_disk_mb"]["median"] == 74.0
    assert row["install_cold_s"]["median"] == 2.0
    assert row["install_cached_s"]["median"] == 2.0


def test_a_store_without_the_core_keeps_its_own_figures(monkeypatch):
    monkeypatch.setattr(compare, "seconds_to_build", lambda candidate, cold: 1.0)
    monkeypatch.setattr(
        compare, "run_worker", lambda candidate, args: worker_answer(1, 0.2)
    )
    base = {"packages": 62, "disk_mb": 176.0}
    candidate = compare.Candidate("raw", ["x==1"], False)

    row = compare.measure_store(candidate, runs=1, base=base)

    assert row["extra_packages"] == 1
    assert row["extra_disk_mb"]["median"] == 0.2


def test_a_store_that_fails_every_run_is_reported_as_failed(monkeypatch):
    monkeypatch.setattr(compare, "seconds_to_build", lambda candidate, cold: 1.0)
    monkeypatch.setattr(
        compare, "run_worker", lambda candidate, args: {"error": "no wheel"}
    )

    row = compare.measure_store(
        compare.CANDIDATES[2], runs=2, base={"packages": 1, "disk_mb": 1}
    )

    assert row == {"error": "no wheel"}


def sample_result() -> dict:
    row = {
        "extra_packages": 56,
        "extra_disk_mb": {"median": 285.0, "min": 284.0, "max": 286.0},
        "install_cold_s": {"median": 50.0, "min": 48.0, "max": 55.0},
        "install_cached_s": {"median": 0.6, "min": 0.6, "max": 0.7},
        "peak_memory_mb": {"median": 220.0, "min": 219.0, "max": 221.0},
        "search_ms_p50": {"median": 1.0, "min": 0.9, "max": 1.1},
        "filter": "works",
    }
    return {
        "runs": 3,
        "chunks": 300,
        "stores": {"Chroma": row, "Broken": {"error": "no wheel"}},
        "scale": {
            "300": {
                "size_mb": {"median": 3.0, "min": 3.0, "max": 3.0},
                "load_s": {"median": 0.3, "min": 0.3, "max": 0.3},
                "search_ms_p50": {"median": 2.4, "min": 2.3, "max": 2.5},
            },
            "30000": {"error": "out of memory"},
        },
        "versions": ["llama-index-core==0.14.25", "chromadb==1.5.9"],
    }


def test_report_has_a_row_for_every_store_and_every_size():
    text = compare.markdown(sample_result())

    assert "| Chroma | 56 | 285.0 (284.0–286.0) |" in text
    assert "| Broken | failed: no wheel |" in text
    assert "| 300 | 3.0 | 0.3 | 2.4 (2.3–2.5) |" in text
    assert "| 30,000 | failed: out of memory |" in text
    assert "Versions: llama-index-core==0.14.25, chromadb==1.5.9." in text


def test_report_says_what_it_does_not_show():
    text = compare.markdown(sample_result())

    assert "nothing here says how well a store finds the right section" in text
    assert "depend on the network" in text


def test_report_leaves_out_the_scale_table_when_it_was_not_measured():
    result = sample_result()
    result["scale"] = {}

    assert "as the chunks grow" not in compare.markdown(result)


def chroma_scale_result() -> dict:
    row = {
        "size_mb": {"median": 40.0, "min": 39.0, "max": 41.0},
        "build_s": {"median": 12.0, "min": 12.0, "max": 12.0},
        "load_s": {"median": 0.8, "min": 0.7, "max": 0.9},
        "search_ms_p50": {"median": 3.2, "min": 3.1, "max": 3.3},
        "peak_memory_mb": {"median": 700.0, "min": 690.0, "max": 710.0},
    }
    return {
        "runs": 3,
        "scale": {"3000": row, "30000": {"error": "out of memory"}},
        "versions": ["chromadb==1.5.9"],
    }


def test_chroma_scale_report_has_a_row_for_every_size():
    text = compare.chroma_scale_markdown(chroma_scale_result())

    assert (
        "| 3,000 | 40.0 (39.0–41.0) | 12.00 | 0.80 (0.70–0.90) | 3.2 (3.1–3.3) |"
        in text
    )
    assert "| 30,000 | failed: out of memory |" in text
    assert "Versions: chromadb==1.5.9." in text


def test_a_scale_worker_exists_for_the_stores_that_are_measured_as_they_grow():
    assert set(compare.SCALE_WORKERS) == {"simple", "chroma"}


class RecordingWorker:
    """Stands in for run_worker: notes which candidate was started and how."""

    def __init__(self):
        self.started = []

    def __call__(self, candidate, arguments):
        self.started.append((candidate.name, arguments))
        return {
            "size_mb": 1.0,
            "build_s": 1.0,
            "load_s": 1.0,
            "search_ms_p50": 1.0,
            "peak_memory_mb": 1.0,
        }


def test_the_chroma_scale_is_measured_in_the_chroma_environment(monkeypatch):
    worker = RecordingWorker()
    monkeypatch.setattr(compare, "run_worker", worker)

    rows = compare.measure_chroma_scale(runs=2)

    assert list(rows) == ["300", "3000", "30000"]
    assert {name for name, _ in worker.started} == {"Chroma (LlamaIndex connector)"}
    assert len(worker.started) == 6
