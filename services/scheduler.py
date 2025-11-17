import asyncio
from typing import Awaitable, Callable, Dict

import discord


class Scheduler:
    def __init__(self, client: discord.Client) -> None:
        self.client = client
        self.tasks: Dict[str, asyncio.Task] = {}

    def schedule(self, identifier: str, delay_seconds: float, coro: Callable[[], Awaitable[None]]) -> None:
        self.cancel(identifier)
        loop = self.client.loop
        task = loop.create_task(self._runner(identifier, delay_seconds, coro))
        self.tasks[identifier] = task

    def cancel(self, identifier: str) -> None:
        task = self.tasks.pop(identifier, None)
        if task is not None and not task.done():
            task.cancel()

    async def _runner(self, identifier: str, delay_seconds: float, coro: Callable[[], Awaitable[None]]) -> None:
        try:
            await asyncio.sleep(delay_seconds)
            await coro()
        finally:
            self.tasks.pop(identifier, None)
