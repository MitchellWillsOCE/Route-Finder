from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

from route_finder.config import CONFIG

T = TypeVar("T")
R = TypeVar("R")


def worker_count() -> int:
    return CONFIG.search_workers


def map_parallel(
    items: Iterable[T],
    fn: Callable[[T], R],
    *,
    max_workers: int | None = None,
) -> list[R]:
    work = list(items)
    if not work:
        return []
    if len(work) == 1:
        return [fn(work[0])]

    workers = max_workers or worker_count()
    workers = min(workers, len(work))
    results: list[R | None] = [None] * len(work)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, item): index for index, item in enumerate(work)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result()
            except Exception:
                results[index] = None
    return [item for item in results if item is not None]
