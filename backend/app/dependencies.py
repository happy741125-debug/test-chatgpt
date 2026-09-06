from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import Database
from app.queue import JobQueue


def get_session(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.database
    yield from database.session()


def get_queue(request: Request) -> JobQueue:
    return request.app.state.queue


SessionDependency = Annotated[Session, Depends(get_session)]
JobQueueDependency = Annotated[JobQueue, Depends(get_queue)]
