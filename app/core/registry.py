from __future__ import annotations

import contextlib
import importlib
import pkgutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from aiogram import Router

if TYPE_CHECKING:
    from app.core.scheduler import ScheduleContext

ScheduleFn = Callable[["ScheduleContext"], Awaitable[None]]
DigestFn = Callable[[], Awaitable[str | None]]


@dataclass(slots=True)
class ModuleSpec:
    """What a feature folder must expose to become part of the bot.

    name      stable id, used for callback prefixes and job namespacing
    title     button label in the main menu
    router    aiogram router holding the module's handlers
    order     main-menu sort position
    schedule  optional: called at boot and after every mutation to (re)build
              this module's jobs from the database
    digest    optional: one short block for the /today summary
    """

    name: str
    title: str
    router: Router
    order: int = 100
    schedule: ScheduleFn | None = None
    digest: DigestFn | None = None


_registry: dict[str, ModuleSpec] = {}


def discover() -> list[ModuleSpec]:
    """Import every app.modules.<x>.module and collect its MODULE spec."""
    if _registry:
        return sorted(_registry.values(), key=lambda m: (m.order, m.title))

    import app.modules as modules_pkg

    for info in pkgutil.iter_modules(modules_pkg.__path__):
        if not info.ispkg or info.name.startswith("_"):
            continue
        # Import models explicitly: a model reaches Base.metadata only when its
        # module is imported. Relying on module.py to import it made a
        # seemingly-unused import load-bearing, one lint autofix away from
        # silently losing the module's tables.
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(f"app.modules.{info.name}.models")

        mod = importlib.import_module(f"app.modules.{info.name}.module")
        spec = getattr(mod, "MODULE", None)
        if not isinstance(spec, ModuleSpec):
            raise RuntimeError(
                f"app/modules/{info.name}/module.py must define MODULE = ModuleSpec(...)"
            )
        _registry[spec.name] = spec

    return sorted(_registry.values(), key=lambda m: (m.order, m.title))
