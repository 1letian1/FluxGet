from pathlib import Path

import httpx
import pytest

from backend.download.models import DownloadTask
from backend.download.path_service import PathService, UnsafePath
from backend.download.retry import RetryPolicy
from backend.download.state_machine import InvalidTaskTransition, TaskStateMachine


@pytest.mark.parametrize("value", ["../escape.txt", "CON", "nul.log", "bad?.txt", ""])
def test_path_service_rejects_unsafe_filenames(value: str) -> None:
    with pytest.raises(UnsafePath):
        PathService.safe_filename(value)


def test_path_service_normalizes_unicode_and_checks_subdirectory() -> None:
    assert PathService.safe_filename("报告 100%.zip") == "报告 100%.zip"
    assert PathService.safe_subdir("资料\\插件") == ("资料", "插件")
    with pytest.raises(UnsafePath):
        PathService.safe_subdir("safe/../outside")


def test_resolved_output_is_contained_in_absolute_root(tmp_path: Path) -> None:
    target, name = PathService.resolve_output_path(str(tmp_path), "safe/nested", "x.zip")

    assert name == "x.zip"
    assert target == tmp_path / "safe" / "nested" / "x.zip"
    with pytest.raises(UnsafePath):
        PathService.resolve_output_path(str(tmp_path), "../outside", "x.zip")


@pytest.mark.parametrize("retryable", [True, False])
def test_retry_policy_classifies_transport_errors(retryable: bool) -> None:
    error = httpx.ConnectError("offline") if retryable else httpx.InvalidURL("bad url")
    assert RetryPolicy.is_retryable(error) is retryable


@pytest.mark.parametrize("status,retryable", [(500, True), (502, True), (503, True), (504, True), (404, False), (501, False)])
def test_retry_policy_classifies_http_status(status: int, retryable: bool) -> None:
    response = httpx.Response(status, request=httpx.Request("GET", "https://example.test"))
    error = httpx.HTTPStatusError("error", request=response.request, response=response)
    assert RetryPolicy.is_retryable(error) is retryable


def test_retry_policy_caps_exponential_delay() -> None:
    assert [RetryPolicy.delay(i) for i in range(4)] == [1.0, 2.0, 4.0, 8.0]
    assert RetryPolicy.delay(20) == 30.0


def test_state_machine_sets_timestamps_and_rejects_terminal_transition() -> None:
    task = DownloadTask.create("https://example.test/a", "a", "C:/downloads")
    downloading = TaskStateMachine.transition(task, "downloading")
    completed = TaskStateMachine.transition(downloading, "completed")

    assert downloading.started_at is not None
    assert completed.finished_at is not None
    with pytest.raises(InvalidTaskTransition):
        TaskStateMachine.transition(completed, "pending")
