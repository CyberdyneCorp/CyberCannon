"""Work the request path hands off rather than waits for (G1).

*"Not in the request path. Mesh loading is unbounded work; an HTTP handler that
waits on it is a timeout with extra steps."* That sentence needs somewhere for
the work to go, and this is it: one queue, one daemon thread per runner, and a
:meth:`BackgroundWork.submit` that returns as soon as the name is on the queue.

It is in the composition root rather than in the application layer because it is
mechanism and not policy.
:func:`~cybercanon.application.use_cases.validation_worker.validate_changed_exports`
knows what to do with a project; this knows only that somebody else will do it
later, which is why the whole of G1 is exercised in the unit layer with no thread
at all and this module has nothing in it to disagree with.

**A repeated submission while the work is already queued is dropped.** The job
takes a project name and validates whatever that project's working copy holds
now, so two notifications arriving together describe one piece of work — and a
queue that grew one entry per webhook would let a chatty repository host turn a
notification storm into a backlog of identical passes.

**A job that raises does not stop the runner.** The failure is handed to
`on_error` (the access log, in the deployment) and the thread goes back to the
queue, because one project's unreadable export must not silently end background
work for every other project.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable

from cybercanon.adapters.wiring.container import Container
from cybercanon.application.ports.repository_host import RepositoryHost
from cybercanon.application.results import Result
from cybercanon.application.use_cases.validation_worker import (
    WorkerReport,
    validate_changed_exports,
)

type Job = Callable[[str], object]
"""What the runner does with a project name. The use case, handed in."""

type ErrorSink = Callable[[str, BaseException], None]
"""Where a job's failure goes. Never nowhere, and never into the caller."""

_STOP = None

DEFAULT_NAME = "canon-background"
JOIN_TIMEOUT_S = 5.0


def ignore(project: str, error: BaseException) -> None:
    """The default sink: a runner nobody configured still must not crash."""


class BackgroundWork:
    """A single worker thread draining a queue of project names.

    Deliberately not a thread pool and deliberately not a distributed queue: the
    design states *"no horizontal scaling of the API beyond one writer per
    project"*, and the validation worker writes. One consumer is therefore the
    correct number, and a second would turn D5's precondition into a lock
    problem for no gain.
    """

    def __init__(
        self,
        job: Job,
        *,
        name: str = DEFAULT_NAME,
        on_error: ErrorSink = ignore,
    ) -> None:
        self._job = job
        self._name = name
        self._on_error = on_error
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._pending: set[str] = set()
        self._running = 0
        self._guard = threading.Lock()
        self._done = threading.Event()
        self._done.set()
        self._thread: threading.Thread | None = None

    def start(self) -> BackgroundWork:
        """Begin draining. Idempotent, so a second call is not a second thread."""
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._drain, name=self._name, daemon=True)
        self._thread.start()
        return self

    def submit(self, project: str) -> None:
        """Queue this project and return. The caller never waits for the job.

        This is the function a router reaches — through the webhook's `refresh`
        callable — and the only thing it may ever do is put a string on a queue.
        """
        with self._guard:
            if project in self._pending:
                return
            self._pending.add(project)
            self._done.clear()
        self._queue.put(project)

    def wait(self, timeout: float | None = None) -> bool:
        """Block until nothing is queued or running. For tests and for shutdown."""
        return self._done.wait(timeout)

    def stop(self, timeout: float = JOIN_TIMEOUT_S) -> None:
        """Ask the thread to finish what is queued and end. Safe to call twice."""
        if self._thread is None:
            return
        self._queue.put(_STOP)
        self._thread.join(timeout)
        self._thread = None

    def __enter__(self) -> BackgroundWork:
        return self.start()

    def __exit__(self, *exception: object) -> None:
        self.stop()

    # -- the thread ------------------------------------------------------

    def _drain(self) -> None:
        """One name at a time, for as long as the process lives."""
        while True:
            project = self._queue.get()
            if project is _STOP:
                self._queue.task_done()
                return
            self._started(project)
            self._run(project)
            self._queue.task_done()

    def _started(self, project: str) -> None:
        """Off the queue and into the job.

        The name leaves `_pending` **before** the job runs, so a notification
        that arrives while this pass is in flight queues another one rather than
        being swallowed by it. Dropping it would mean a commit that landed
        mid-pass was never validated until the next fetch timer — the quiet
        staleness D4 refuses, one layer down.
        """
        with self._guard:
            self._pending.discard(project)
            self._running += 1

    def _run(self, project: str) -> None:
        """One job, whose failure is reported and never allowed to end the thread."""
        try:
            self._job(project)
        except BaseException as failure:  # one project's failure is not the runner's
            self._on_error(project, failure)
        finally:
            self._finished(project)

    def _finished(self, project: str) -> None:
        with self._guard:
            self._running -= 1
            if not self._pending and not self._running:
                self._done.set()


def validation_job(container: Container, repository_host: RepositoryHost) -> Job:
    """The job the API deployment runs off the request path: G1's worker.

    A closure over one project's ports rather than a class, because there is
    nothing to configure: the use case decides what has changed, what to
    validate and what to commit, and this only supplies the ports it was wired
    with. The container is the same one the read surface serves from, so the
    verdict the worker commits is the verdict that surface would print.
    """

    def run(project: str) -> Result[WorkerReport]:
        return validate_changed_exports(
            project,
            repository_host=repository_host,
            spec_store=container.spec_store,
            mesh_inspector=container.mesh_inspector,
            blob_store=container.blob_store,
            search_index=container.search_index,
        )

    return run


__all__ = [
    "DEFAULT_NAME",
    "JOIN_TIMEOUT_S",
    "BackgroundWork",
    "ErrorSink",
    "Job",
    "ignore",
    "validation_job",
]
