import asyncio
import inspect
from abc import ABC, abstractmethod
from typing import Callable, Any, Dict, List
from app.core.logging import logger


class JobQueue(ABC):
    """Interface abstrata para fila de jobs desacoplada do framework de enfileiramento."""

    @abstractmethod
    async def enqueue(self, task: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        pass


class AsyncInMemoryJobQueue(JobQueue):
    """Implementação assíncrona local para execução de tarefas em background sem Redis inicial."""

    def __init__(self):
        self._running_tasks: List[asyncio.Task] = []

    async def enqueue(self, task: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        async def _wrapper():
            try:
                if inspect.iscoroutinefunction(task):
                    await task(*args, **kwargs)
                else:
                    await asyncio.to_thread(task, *args, **kwargs)
            except Exception as e:
                logger.error(f"Erro na execução da tarefa em background {task.__name__}: {e}", exc_info=True)

        async_task = asyncio.create_task(_wrapper())
        self._running_tasks.append(async_task)
        async_task.add_done_callback(lambda t: self._running_tasks.remove(t) if t in self._running_tasks else None)


job_queue = AsyncInMemoryJobQueue()
