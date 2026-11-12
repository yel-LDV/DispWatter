from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("DispWatter.WorkerPool")


class WorkerPool:
    """Gestiona 3 threads dedicados (device, panel, system) con colas queue.Queue.
    
    Cada thread ejecuta tareas encoladas desde el loop de asyncio y devuelve
    resultados vía asyncio.Future resuelto con call_soon_threadsafe.
    """

    def __init__(self) -> None:
        self._queues: Dict[str, queue.Queue] = {
            "device": queue.Queue(),
            "panel": queue.Queue(),
            "system": queue.Queue(),
        }
        self._threads: Dict[str, threading.Thread] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Inicia los 3 threads dedicados."""
        if self._running:
            return
        self._running = True
        self._loop = loop or asyncio.get_running_loop()

        for name in ("device", "panel", "system"):
            t = threading.Thread(
                target=self._worker_loop,
                args=(name,),
                name=f"worker-{name}",
                daemon=True,
            )
            self._threads[name] = t
            t.start()
            logger.info("Thread %s iniciado", name)

    def stop(self) -> None:
        """Detiene todos los threads de forma graceful."""
        if not self._running:
            return
        self._running = False
        # Enviar None a cada cola para que los threads terminen
        for name, q in self._queues.items():
            q.put(None)
        for name, t in self._threads.items():
            t.join(timeout=5.0)
            logger.info("Thread %s detenido", name)
        self._threads.clear()

    def _worker_loop(self, name: str) -> None:
        """Bucle infinito del thread que procesa tareas de la cola."""
        q: queue.Queue = self._queues[name]
        logger.info("Worker %s listo para procesar tareas", name)
        while self._running:
            try:
                task = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if task is None:
                # Señal de parada
                break
            action = task.get("action")
            params = task.get("params", {})
            future = task.get("future")
            try:
                result = self._dispatch(name, action, params)
                if future and self._loop:
                    self._loop.call_soon_threadsafe(future.set_result, result)
            except Exception as exc:
                logger.exception("Error en worker %s acción %s", name, action)
                if future and self._loop:
                    self._loop.call_soon_threadsafe(
                        future.set_exception, exc
                    )
            finally:
                q.task_done()

    def _dispatch(
        self, worker_name: str, action: str, params: Dict[str, Any]
    ) -> Any:
        """Despacha la acción al módulo correspondiente."""
        if worker_name == "device":
            from backend.workers.device_worker import handle as device_handle
            return device_handle(action, params)
        elif worker_name == "panel":
            from backend.workers.panel_worker import handle as panel_handle
            return panel_handle(action, params)
        elif worker_name == "system":
            from backend.workers.system_worker import handle as system_handle
            return system_handle(action, params)
        else:
            raise ValueError(f"Worker desconocido: {worker_name}")

    async def submit(
        self, worker_name: str, action: str, **params: Any
    ) -> Any:
        """Envía una tarea a un worker y espera el resultado.
        
        Args:
            worker_name: "device", "panel" o "system"
            action: nombre de la acción a ejecutar
            **params: parámetros de la acción
            
        Returns:
            El resultado de la acción
        """
        if not self._running:
            raise RuntimeError("WorkerPool no está en ejecución")
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        task = {
            "action": action,
            "params": params,
            "future": future,
        }
        self._queues[worker_name].put(task)
        return await future

    @property
    def device_queue(self) -> queue.Queue:
        return self._queues["device"]

    @property
    def panel_queue(self) -> queue.Queue:
        return self._queues["panel"]

    @property
    def system_queue(self) -> queue.Queue:
        return self._queues["system"]


# Singleton global
worker_pool = WorkerPool()
