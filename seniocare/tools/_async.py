"""
Run synchronous tools off the event loop (AUDIT R-01).

ADK calls a synchronous tool function directly on the event loop
(``FunctionTool._invoke_callable``: ``target(**args)`` when the function is
not a coroutine). Every data tool here does blocking psycopg2 queries and the
search tools do blocking ``requests`` calls, so each tool call froze the
whole server, including every other user's SSE stream, for its duration.

``threaded(fn)`` wraps a synchronous tool in an ``async def`` that runs it in
the default thread pool. ``functools.wraps`` keeps the name, docstring and,
through ``__wrapped__``, the signature, so ADK still derives the same tool
schema and still injects ``tool_context``. The tools themselves stay
synchronous and directly testable.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable


def threaded(fn: Callable[..., Any]) -> Callable[..., Any]:
    if asyncio.iscoroutinefunction(fn):
        return fn

    @functools.wraps(fn)
    async def runner(**kwargs: Any) -> Any:
        return await asyncio.to_thread(fn, **kwargs)

    return runner
