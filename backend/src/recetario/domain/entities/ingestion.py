"""Ingestion-job domain entity — pure, framework-free.

A long-running recipe import (scrape a URL, later: LLM-structure a transcript) is
modeled as a *job* so the API can return immediately and the UI polls for status.
The job decouples the request from the work and leaves room to graduate the
in-process worker to a real queue without touching the API contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IngestionInputType(str, Enum):
    """How the source should be fetched. Only WEB is wired in this slice."""

    WEB = "web"
    VIDEO = "video"


@dataclass
class IngestionJob:
    input_url: str
    input_type: IngestionInputType = IngestionInputType.WEB
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    result_recipe_id: int | None = None
    error: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def mark_running(self) -> None:
        self.status = JobStatus.RUNNING
        self.progress = max(self.progress, 10)

    def mark_succeeded(self, recipe_id: int) -> None:
        self.status = JobStatus.SUCCEEDED
        self.progress = 100
        self.result_recipe_id = recipe_id
        self.error = None

    def mark_failed(self, message: str) -> None:
        self.status = JobStatus.FAILED
        self.error = message
