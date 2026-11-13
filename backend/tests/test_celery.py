"""Celery transport, serialization and task discovery without external services."""
import importlib
import importlib.util
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from kombu import Connection
from kombu.message import Message
from celery.worker.request import Request as WorkerRequest
from app.core.config import Settings


class CeleryTests(unittest.TestCase):
    def celery_app(self):
        self.assertIsNotNone(
            importlib.util.find_spec("app.celery_app"), "Celery application entry point is missing"
        )
        return importlib.import_module("app.celery_app").celery_app

    def test_broker_url_preserves_special_credentials_and_vhost(self):
        settings = Settings()
        settings.RABBITMQ_HOST = "rabbitmq"
        settings.RABBITMQ_PORT = 5673
        settings.RABBITMQ_USER = "task@user:worker"
        settings.RABBITMQ_PASSWORD = "p@ss:/?#%中文"
        settings.RABBITMQ_VHOST = "/team tasks/中文"

        self.assertTrue(hasattr(settings, "CELERY_BROKER_URL"), "RabbitMQ URL builder is missing")
        with Connection(settings.CELERY_BROKER_URL) as connection:
            self.assertEqual(connection.hostname, "rabbitmq")
            self.assertEqual(connection.port, 5673)
            self.assertEqual(connection.userid, "task@user:worker")
            self.assertEqual(connection.password, "p@ss:/?#%中文")
            self.assertEqual(connection.virtual_host, "/team tasks/中文")
            self.assertEqual(connection.transport.driver_name, "py-amqp")

    def test_default_rabbitmq_vhost_uses_an_encoded_root_path(self):
        settings = Settings()
        settings.RABBITMQ_HOST = "rabbitmq"
        settings.RABBITMQ_PORT = 5672
        settings.RABBITMQ_USER = "sudothink"
        settings.RABBITMQ_PASSWORD = ""
        settings.RABBITMQ_VHOST = "/"
        self.assertTrue(hasattr(settings, "CELERY_BROKER_URL"), "RabbitMQ URL builder is missing")
        self.assertEqual(settings.CELERY_BROKER_URL, "amqp://sudothink:@rabbitmq:5672/%2F")
        with Connection(settings.CELERY_BROKER_URL) as connection:
            self.assertEqual(connection.virtual_host, "/")

    def test_workers_accept_only_json_and_retry_broker_startup(self):
        app = self.celery_app()
        self.assertEqual(app.conf.task_serializer, "json")
        self.assertEqual(app.conf.result_serializer, "json")
        self.assertEqual(app.conf.accept_content, ["json"])
        self.assertEqual(app.conf.result_accept_content, ["json"])
        self.assertTrue(app.conf.broker_connection_retry_on_startup)
        self.assertEqual(app.conf.worker_prefetch_multiplier, 1)

    def test_article_views_use_delayed_once_jobs_without_a_global_beat_scan(self):
        app = self.celery_app()
        self.assertEqual(app.conf.beat_schedule, {})

    def test_delayed_wrapper_is_discovered_with_worker_loss_protection(self):
        app = self.celery_app()
        app.loader.import_default_modules()
        task = app.tasks["app.tasks.delayed.execute_once"]
        self.assertTrue(task.acks_late)
        self.assertFalse(task.acks_on_timeout)
        self.assertTrue(task.reject_on_worker_lost)
        self.assertEqual(task.max_retries, 5)

    def test_delayed_wrapper_hard_timeout_requeues_instead_of_acknowledging_job(self):
        app = self.celery_app()
        app.loader.import_default_modules()
        task = app.tasks["app.tasks.delayed.execute_once"]
        acked, rejected = [], []
        message = Message(
            body=([], {}, {}), headers={"id": uuid4().hex, "task": task.name},
            delivery_info={"exchange": "sudothink", "routing_key": "sudothink"},
        )
        request = WorkerRequest(
            message, app=app, task=task, decoded=True,
            on_ack=lambda *args: acked.append(args),
            on_reject=lambda *args: rejected.append(args),
        )
        # Only replace the backend write; execute Celery's real timeout/ACK path.
        with patch.object(task.backend, "mark_as_failure"), patch("celery.worker.request.error"):
            request.on_timeout(soft=False, timeout=300)
        self.assertEqual(acked, [])
        self.assertEqual(len(rejected), 1)
        self.assertIs(rejected[0][-1], True)

    def test_task_and_control_routing_are_isolated_on_a_shared_vhost(self):
        app = self.celery_app()
        queue = app.amqp.queues["sudothink"]
        self.assertEqual(queue.exchange.name, "sudothink")
        self.assertEqual(queue.routing_key, "sudothink")
        self.assertEqual(app.control.mailbox.exchange.name, "sudothink.pidbox")

    def test_discovered_ping_executes_without_services_and_can_return_results(self):
        app = self.celery_app()
        app.loader.import_default_modules()
        task = app.tasks["app.tasks.diagnostics.ping"]
        self.assertFalse(task.ignore_result)
        result = task.apply()
        self.assertTrue(result.successful())
        self.assertEqual(result.get(), "pong")

    def test_entrypoint_import_and_discovery_do_not_initialize_web_resources(self):
        code = """
import sys
from app.celery_app import celery_app
celery_app.loader.import_default_modules()
assert not {'app.server', 'app.core.redis', 'app.models', 'sanic', 'tortoise'} & sys.modules.keys()
assert celery_app.tasks['app.tasks.diagnostics.ping'].apply().get() == 'pong'
assert 'app.tasks.delayed.execute_once' in celery_app.tasks
assert 'app.tasks.article_views.persist_article_views' in celery_app.tasks
"""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_direct_task_import_uses_the_configured_application(self):
        code = """
from app.tasks.diagnostics import ping
assert ping.app.main == 'sudothink'
assert ping.app.conf.task_default_queue == 'sudothink'
assert ping.apply().get() == 'pong'
"""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_environment_configures_worker_and_optional_result_backend(self):
        code = """
from app.celery_app import celery_app
assert celery_app.conf.worker_concurrency == 3
assert celery_app.conf.timezone == 'UTC'
assert celery_app.backend.__class__.__name__ == 'RPCBackend'
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            env={
                **os.environ,
                "CELERY_WORKER_CONCURRENCY": "3",
                "CELERY_TIMEZONE": "UTC",
                "CELERY_RESULT_BACKEND": "rpc://",
            },
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_default_worker_configuration_disables_result_storage(self):
        code = """
from app.celery_app import celery_app
assert celery_app.conf.worker_concurrency == 2
assert celery_app.conf.timezone == 'Asia/Shanghai'
assert celery_app.backend.__class__.__name__ == 'DisabledBackend'
"""
        env = dict(os.environ)
        for name in ("CELERY_WORKER_CONCURRENCY", "CELERY_TIMEZONE", "CELERY_RESULT_BACKEND"):
            env.pop(name, None)
        result = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_worker_concurrency_keeps_bounded_default(self):
        code = """
from app.celery_app import celery_app
assert celery_app.conf.worker_concurrency == 2
"""
        for value in ("0", "-2", "invalid"):
            with self.subTest(value=value):
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    env={**os.environ, "CELERY_WORKER_CONCURRENCY": value},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
