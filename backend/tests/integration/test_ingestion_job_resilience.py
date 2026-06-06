"""Regression test for SqlAlchemyIngestionJobRepository.update (issue #7).

The ingestion worker shares one DB session across repos. If a sibling repo
poisons the transaction (e.g. a failed flush), recording the job's terminal
status must still succeed — otherwise the job wedges in 'running' forever and
the UI polls indefinitely. `update` recovers by rolling back and retrying once.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from recetario.domain.entities import IngestionInputType, IngestionJob, JobStatus
from recetario.infrastructure.db.models import NutrientModel
from recetario.infrastructure.db.repositories import SqlAlchemyIngestionJobRepository


@pytest.fixture
def session(db_engine: Engine) -> Session:
    with Session(db_engine, future=True) as s:
        yield s


def _poison(session: Session) -> None:
    """Leave the session in a pending-rollback state, as a failed flush would.

    Inserts a duplicate `usda_nutrient_id` (a unique column), commits, and does
    NOT roll back — so the next use of the session raises until rolled back.
    """
    session.add(NutrientModel(usda_nutrient_id=99999, name="X", unit="g"))
    session.commit()
    session.add(NutrientModel(usda_nutrient_id=99999, name="Dup", unit="g"))
    with pytest.raises(IntegrityError):
        session.commit()  # poisons the transaction; intentionally no rollback


def test_update_records_terminal_status_despite_poisoned_session(session: Session) -> None:
    jobs = SqlAlchemyIngestionJobRepository(session)
    job = jobs.add(
        IngestionJob(input_url="https://example.com/r", input_type=IngestionInputType.WEB)
    )
    assert job.id is not None

    _poison(session)

    # Without the rollback-and-retry, this raises PendingRollbackError and the
    # job is never marked failed. With the fix, it recovers.
    job.mark_failed("Unexpected error: boom")
    updated = jobs.update(job)

    assert updated is not None
    assert updated.status is JobStatus.FAILED
    assert updated.error == "Unexpected error: boom"

    # And it's durably persisted: a fresh repo on a new session reads it back.
    with Session(session.get_bind(), future=True) as fresh:
        reread = SqlAlchemyIngestionJobRepository(fresh).get(job.id)
        assert reread is not None
        assert reread.status is JobStatus.FAILED
