"""Background worker package.

Entrypoints:
- ``python -m app.worker`` (``app.worker.__main__``)
- ``app.worker.main:main``

The worker polls the `Pipeline Jobs` tab, claims one eligible job, runs the
configured stage, persists progress, and repeats. One worker instance only.
"""

from __future__ import annotations

from .main import Worker, main
from .pipeline import ProfileFetchStage, Stage, StageOutcome

__all__ = ["ProfileFetchStage", "Stage", "StageOutcome", "Worker", "main"]
