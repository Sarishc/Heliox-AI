"""Celery entry point for the real worker test only: the real tasks, with the fake adapter and a private queue."""

import os

from ledger_worker_fake import ConfiguredAdapter

import app.services.ledger_shadow.orchestrator as orchestrator
from app.celery_app import celery_app

orchestrator._default_adapter = lambda provider, config: ConfiguredAdapter(config)
celery_app.conf.task_default_queue = os.environ["LEDGER_TEST_QUEUE"]
