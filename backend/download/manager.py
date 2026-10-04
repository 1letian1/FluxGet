"""Queue scheduler, HTTP workers, retries, resume, cancellation and conflicts."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from backend.download.events import EventBus
from backend.download.models import DownloadTask, SourceType
from backend.download.path_service import PathService, UnsafePath
from backend.download.repository import TaskRepository
from backend.download.retry import RetryPolicy
from backend.download.state_machine import InvalidTaskTransition, TaskStateMachine

logger = logging.getLogger(__name__)


class DownloadManager:
    WORKER_COUNT = 32

    def __init__(self, repository: TaskRepository, *, concurrency: int = 4, max_retries: int = 3,
                 conflict_policy: str = "ask", client: httpx.AsyncClient | None = None,
                 event_bus: EventBus | None = None) -> None:
        self.repository = repository
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.conflict_policy = conflict_policy
        self.events = event_bus or EventBus()
        self.client = client or httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60.0, connect=15.0))
        self._owns_client = client is None
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._running: dict[str, asyncio.Task[Any]] = {}
        self._cancel_requested: set[str] = set()
        self._slot_condition = asyncio.Condition()
        self._active_slots = 0
        self._closing = False
        self._started = False
        self._last_progress: dict[str, tuple[float, int]] = {}
        self._delayed_retries: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        if self._started:
            return
        self._closing = False
        tasks = await self.repository.recover_interrupted()
        logger.info("Download manager started with %d active tasks after recovery", len(tasks),
                    extra={"event": "recovery.complete"})
        self._workers = [asyncio.create_task(self._worker(), name=f"download-worker-{i}")
                         for i in range(self.WORKER_COUNT)]
        self._started = True
        for task in tasks:
            if task.status == "pending":
                self._queue.put_nowait(task.id)

    async def close(self) -> None:
        if not self._started:
            if self._owns_client:
                await self.client.aclose()
            return
        self._closing = True
        delayed = tuple(self._delayed_retries)
        for task in delayed:
            task.cancel()
        if delayed:
            await asyncio.gather(*delayed, return_exceptions=True)
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._started = False
        if self._owns_client:
            await self.client.aclose()
        logger.info("Download manager stopped; resumable tasks remain persisted",
                    extra={"event": "shutdown.complete"})

    async def configure(self, *, concurrency: int, max_retries: int, conflict_policy: str) -> None:
        async with self._slot_condition:
            self.concurrency = concurrency
            self.max_retries = max_retries
            self.conflict_policy = conflict_policy
            self._slot_condition.notify_all()

    async def create_task(self, url: str, filename: str, root: str, subdir: str = "", *,
                          source_type: SourceType = "direct", rule_id: str | None = None) -> DownloadTask:
        try:
            parsed = httpx.URL(url)
        except httpx.InvalidURL as exc:
            raise ValueError("URL is malformed") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.host or parsed.username or parsed.password:
            raise ValueError("Only absolute HTTP/HTTPS URLs without credentials are allowed")
        target, safe_name = PathService.resolve_output_path(root, subdir, filename)
        task = DownloadTask.create(url, safe_name, str(target.parent), source_type=source_type,
                                   rule_id=rule_id, max_retries=self.max_retries,
                                   conflict_policy=self.conflict_policy, output_root=root, subdir=subdir)
        await self.repository.create(task)
        logger.info("Download task created", extra={"event": "task.created", "task_id": task.id,
                    "download_filename": task.filename, "url": self._safe_log_url(task.url), "status": task.status})
        self.events.publish("task.created", task.to_dict())
        if not self._started:
            await self.start()
        self._queue.put_nowait(task.id)
        return task

    async def get_task(self, task_id: str) -> DownloadTask | None:
        return await self.repository.get(task_id)

    async def list_tasks(self, *, active_only: bool = True, limit: int = 500, offset: int = 0) -> list[DownloadTask]:
        return await self.repository.list(active_only=active_only, limit=limit, offset=offset)

    async def cancel(self, task_id: str) -> DownloadTask:
        task = await self._require(task_id)
        if task.status == "pending":
            updated = await self._transition(task, "cancelled", error_code=None, error_message=None)
            if updated.status == "cancelled":
                return updated
            task = updated
        if task.status == "downloading":
            self._cancel_requested.add(task_id)
            running = self._running.get(task_id)
            if running:
                running.cancel()
        else:
            raise InvalidTaskTransition(f"Task in {task.status} state cannot be cancelled")
        updated = await self._require(task_id)
        return updated

    async def retry(self, task_id: str) -> DownloadTask:
        task = await self._require(task_id)
        if task.status not in {"failed", "cancelled"}:
            raise InvalidTaskTransition("Only failed or cancelled tasks can be retried")
        updated = TaskStateMachine.transition(task, "pending", retry_count=0, error_code=None,
                                             error_message=None, bytes_downloaded=self._part_size(task))
        await self._save(updated, "task.retrying")
        self._queue.put_nowait(task_id)
        return updated

    async def resolve_conflict(self, task_id: str, resolution: str) -> DownloadTask:
        if resolution not in {"overwrite", "rename", "skip"}:
            raise ValueError("resolution must be overwrite, rename, or skip")
        task = await self._require(task_id)
        if task.status != "waiting_user":
            raise InvalidTaskTransition("Task is not waiting for a conflict decision")
        if resolution == "skip":
            updated = TaskStateMachine.transition(task, "skipped", error_code="conflict_skipped",
                                                  error_message="Skipped because the destination already exists")
            await self._save(updated, "task.skipped")
            return updated
        filename = task.filename
        if resolution == "rename":
            filename = self._unique_name(Path(task.output_dir), filename)
        target = Path(task.output_dir) / filename
        temp_path = task.temp_path
        if resolution == "rename" and Path(task.temp_path).exists():
            new_temp_path = str(target) + ".part"
            if Path(new_temp_path).exists():
                filename = self._unique_name(Path(task.output_dir), filename)
                target = Path(task.output_dir) / filename
                new_temp_path = str(target) + ".part"
            os.replace(task.temp_path, new_temp_path)
            temp_path = new_temp_path
        updated = TaskStateMachine.transition(task, "pending", filename=filename,
                                              temp_path=temp_path, conflict_policy=resolution,
                                              error_code=None, error_message=None)
        await self._save(updated, "task.retrying")
        self._queue.put_nowait(task_id)
        return updated

    async def _worker(self) -> None:
        while True:
            task_id = await self._queue.get()
            try:
                task = await self.repository.get(task_id)
                if task is None or task.status != "pending" or self._closing:
                    continue
                await self._acquire_slot()
                try:
                    await self._run_task(task_id)
                    if self._closing:
                        return
                finally:
                    async with self._slot_condition:
                        self._active_slots -= 1
                        self._slot_condition.notify_all()
            except asyncio.CancelledError:
                if self._closing:
                    return
                raise
            finally:
                self._queue.task_done()

    async def _acquire_slot(self) -> None:
        async with self._slot_condition:
            await self._slot_condition.wait_for(lambda: self._closing or self._active_slots < self.concurrency)
            if self._closing:
                raise asyncio.CancelledError
            self._active_slots += 1

    async def _run_task(self, task_id: str) -> None:
        task = await self.repository.get(task_id)
        if task is None or task.status != "pending":
            return
        try:
            task = await self._transition(task, "downloading", error_code=None, error_message=None)
            if task.status != "downloading":
                return
            self._running[task_id] = asyncio.current_task()
            if task_id in self._cancel_requested:
                raise asyncio.CancelledError
            target, safe_name = PathService.resolve_output_path(task.output_root, task.subdir, task.filename)
            task = task.changed(filename=safe_name, output_dir=str(target.parent), temp_path=str(target) + ".part")
            part_path = Path(task.temp_path)
            if part_path.is_symlink() or (part_path.exists() and not part_path.is_file()):
                raise UnsafePath("Partial download path is not a regular file")
            await self.repository.save(task)
            target_dir = target.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            if target.exists() and task.conflict_policy == "ask":
                await self._transition(task, "waiting_user", error_code="file_exists",
                                        error_message="A file with this name already exists")
                return
            if target.exists() and task.conflict_policy == "skip":
                await self._transition(task, "skipped", error_code="file_exists",
                                        error_message="Skipped because the destination already exists")
                return
            if target.exists() and task.conflict_policy == "rename":
                task = await self._rename_destination(task)
            await self._transfer(task)
        except asyncio.CancelledError:
            current = await self.repository.get(task_id)
            if current and current.status == "downloading":
                if task_id in self._cancel_requested:
                    await self._transition(current, "cancelled", error_code=None, error_message=None,
                                           bytes_downloaded=self._part_size(current))
                elif self._closing:
                    await self._transition(current, "pending", bytes_downloaded=self._part_size(current))
                else:
                    await self._transition(current, "cancelled", error_code=None, error_message=None,
                                           bytes_downloaded=self._part_size(current))
            if not self._closing and task_id not in self._cancel_requested:
                raise
        except (UnsafePath, OSError) as exc:
            current = await self.repository.get(task_id)
            if current and current.status == "downloading":
                await self._transition(current, "failed", error_code="path_or_disk_error",
                                        error_message=self._safe_error(exc))
        except Exception as exc:
            await self._handle_failure(task_id, exc)
        finally:
            self._running.pop(task_id, None)
            self._cancel_requested.discard(task_id)
            self._last_progress.pop(task_id, None)

    async def _transfer(self, task: DownloadTask) -> None:
        part = Path(task.temp_path)
        target = Path(task.output_dir) / task.filename
        existing = self._part_size(task)
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        async with self.client.stream("GET", task.url, headers=headers) as response:
            if response.status_code == 416 and existing:
                total = self._unsatisfied_range_total(response.headers.get("content-range"))
                if total == existing:
                    await self._commit_file(task, target)
                    return
            response.raise_for_status()
            append = bool(existing and response.status_code == 206)
            if response.status_code == 206 and not existing:
                raise httpx.HTTPStatusError("Server returned partial content without a Range request", request=response.request, response=response)
            if existing and response.status_code == 200:
                existing = 0
            if existing and response.status_code != 206:
                raise httpx.HTTPStatusError("Server returned an invalid response to a Range request", request=response.request, response=response)
            content_length = response.headers.get("content-length")
            try:
                response_length = int(content_length) if content_length is not None else None
            except ValueError:
                response_length = None
            total = (existing + response_length) if response_length is not None else None
            if response.status_code == 206:
                range_start = self._content_range_start(response.headers.get("content-range"))
                if append and range_start != existing:
                    raise httpx.HTTPStatusError("Server returned an invalid Content-Range", request=response.request, response=response)
                range_total = self._content_range_total(response.headers.get("content-range"))
                if range_total is not None:
                    total = range_total
            task = task.changed(bytes_total=total, bytes_downloaded=existing)
            await self.repository.save(task)
            part.parent.mkdir(parents=True, exist_ok=True)
            written = existing
            mode = "ab" if append else "wb"
            with part.open(mode) as output:
                async for chunk in response.aiter_raw(128 * 1024):
                    if not chunk:
                        continue
                    output.write(chunk)
                    written += len(chunk)
                    now = asyncio.get_running_loop().time()
                    previous = self._last_progress.get(task.id)
                    if previous is None or now - previous[0] >= 0.2:
                        speed = (max(0.0, (written - previous[1]) / (now - previous[0]))
                                 if previous is not None and now > previous[0] else None)
                        self._last_progress[task.id] = (now, written)
                        current = task.changed(bytes_downloaded=written, bytes_total=total)
                        await self.repository.save(current)
                        self.events.publish("task.progress", {**current.to_dict(), "speed_bytes_per_second": speed})
                output.flush()
                os.fsync(output.fileno())
        latest = await self.repository.get(task.id)
        if latest is None or latest.status != "downloading":
            return
        latest = latest.changed(bytes_downloaded=self._part_size(latest), bytes_total=total)
        await self.repository.save(latest)
        if target.exists() and latest.conflict_policy == "ask":
            await self._transition(latest, "waiting_user", error_code="file_exists",
                                    error_message="A file with this name appeared during the download")
            return
        if target.exists() and latest.conflict_policy == "skip":
            await self._transition(latest, "skipped", error_code="file_exists",
                                    error_message="Skipped because the destination already exists")
            return
        await self._commit_file(latest, target)

    async def _commit_file(self, task: DownloadTask, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        current = await self.repository.get(task.id)
        if current is None or current.status != "downloading":
            return
        if target.exists() and current.conflict_policy == "ask":
            await self._transition(current, "waiting_user", error_code="file_exists",
                                    error_message="A file with this name appeared before the download could be committed")
            return
        if target.exists() and current.conflict_policy == "skip":
            await self._transition(current, "skipped", error_code="file_exists",
                                    error_message="Skipped because the destination already exists")
            return
        if target.exists() and current.conflict_policy == "rename":
            current = await self._rename_destination(current)
            target = Path(current.output_dir) / current.filename
        os.replace(current.temp_path, target)
        if current and current.status == "downloading":
            await self._transition(current, "completed", bytes_downloaded=target.stat().st_size,
                                   error_code=None, error_message=None)

    async def _rename_destination(self, task: DownloadTask) -> DownloadTask:
        filename = self._unique_name(Path(task.output_dir), task.filename)
        target = Path(task.output_dir) / filename
        temp_path = task.temp_path
        if Path(task.temp_path).exists():
            new_temp_path = str(target) + ".part"
            if Path(new_temp_path).exists():
                filename = self._unique_name(Path(task.output_dir), filename)
                target = Path(task.output_dir) / filename
                new_temp_path = str(target) + ".part"
            os.replace(task.temp_path, new_temp_path)
            temp_path = new_temp_path
        updated = task.changed(filename=filename, temp_path=temp_path)
        await self.repository.save(updated)
        logger.info("Download destination renamed", extra={"event": "task.renamed", "task_id": task.id,
                    "download_filename": updated.filename, "url": self._safe_log_url(updated.url),
                    "status": updated.status})
        self.events.publish("task.updated", updated.to_dict())
        return updated

    async def _handle_failure(self, task_id: str, error: Exception) -> None:
        current = await self.repository.get(task_id)
        if current is None or current.status != "downloading":
            return
        if task_id in self._cancel_requested:
            await self._transition(current, "cancelled", bytes_downloaded=self._part_size(current))
            return
        if RetryPolicy.is_retryable(error) and current.retry_count < current.max_retries and not self._closing:
            count = current.retry_count + 1
            pending = TaskStateMachine.transition(
                current, "pending", retry_count=count, bytes_downloaded=self._part_size(current),
                error_code="retrying", error_message=self._safe_error(error),
            )
            await self._save(pending, "task.retrying")
            delayed = asyncio.create_task(self._requeue_after(task_id, RetryPolicy.delay(count - 1)))
            self._delayed_retries.add(delayed)
            delayed.add_done_callback(self._delayed_retries.discard)
            return
        code = f"http_{error.response.status_code}" if isinstance(error, httpx.HTTPStatusError) else type(error).__name__.lower()
        await self._transition(current, "failed", bytes_downloaded=self._part_size(current),
                               error_code=code, error_message=self._safe_error(error))

    async def _requeue_after(self, task_id: str, delay: float) -> None:
        await asyncio.sleep(delay)
        latest = await self.repository.get(task_id)
        if latest and latest.status == "pending" and task_id not in self._cancel_requested and not self._closing:
            self._queue.put_nowait(task_id)

    async def _transition(self, task: DownloadTask, status: str, **changes: object) -> DownloadTask:
        updated = TaskStateMachine.transition(task, status, **changes)
        event_type = {
            "downloading": "task.started", "waiting_user": "task.waiting_user",
            "completed": "task.completed", "failed": "task.failed",
            "cancelled": "task.cancelled", "skipped": "task.skipped",
            "pending": "task.retrying",
        }.get(status, "task.updated")
        saved = await self.repository.save(updated, expected_status=task.status)
        if not saved:
            return await self._require(task.id)
        logger.info("Download task state changed to %s", status,
                    extra={"event": event_type, "task_id": task.id, "download_filename": updated.filename,
                           "url": self._safe_log_url(updated.url), "status": status,
                           "error_code": updated.error_code})
        self.events.publish(event_type, updated.to_dict())
        return updated

    async def _save(self, task: DownloadTask, event_type: str) -> None:
        await self.repository.save(task)
        logger.info("Download task update: %s", event_type,
                    extra={"event": event_type, "task_id": task.id, "download_filename": task.filename,
                           "url": self._safe_log_url(task.url), "status": task.status,
                           "error_code": task.error_code})
        self.events.publish(event_type, task.to_dict())

    async def _require(self, task_id: str) -> DownloadTask:
        task = await self.repository.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    @staticmethod
    def _part_size(task: DownloadTask) -> int:
        try:
            return Path(task.temp_path).stat().st_size
        except OSError:
            return 0

    @staticmethod
    def _safe_error(error: BaseException) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"The server returned HTTP {error.response.status_code}"
        if isinstance(error, httpx.TimeoutException):
            return "The download timed out"
        if isinstance(error, httpx.ConnectError):
            return "Could not connect to the download server"
        if isinstance(error, (OSError, UnsafePath)):
            return "Could not access or write the selected download location"
        return "The download failed due to a network or server error"

    @staticmethod
    def _safe_log_url(url: str) -> str:
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname or ""
            if ":" in hostname:
                hostname = f"[{hostname}]"
            if parsed.port is not None:
                hostname = f"{hostname}:{parsed.port}"
            return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))
        except ValueError:
            return "<invalid-url>"

    @staticmethod
    def _content_range_total(value: str | None) -> int | None:
        if not value or "/" not in value:
            return None
        total = value.rsplit("/", 1)[1]
        return int(total) if total.isdigit() else None

    @staticmethod
    def _content_range_start(value: str | None) -> int | None:
        if not value or not value.startswith("bytes ") or "-" not in value:
            return None
        start = value[6:].split("-", 1)[0]
        return int(start) if start.isdigit() else None

    @staticmethod
    def _unsatisfied_range_total(value: str | None) -> int | None:
        return DownloadManager._content_range_total(value)

    @staticmethod
    def _unique_name(directory: Path, filename: str) -> str:
        path = Path(filename)
        stem, suffix = path.stem, path.suffix
        candidate = filename
        index = 1
        while (directory / candidate).exists():
            candidate = f"{stem} ({index}){suffix}"
            index += 1
        while (directory / f"{candidate}.part").exists():
            candidate = f"{stem} ({index}){suffix}"
            index += 1
        return PathService.safe_filename(candidate)
