from celery import Celery
from celery.schedules import crontab

from . import config
from .db import connect, init_db, now

app = Celery("parking_checker", broker=config.BROKER_URL)
app.conf.update(
    timezone=config.TIMEZONE,
    enable_utc=True,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=2,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 3},
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    task_default_queue=config.TASK_QUEUE,
    beat_schedule={
        "hourly-ticket-check": {
            "task": "parking.check_all",
            "schedule": crontab(minute=0)
            if config.CHECK_INTERVAL_SECONDS == 3600
            else config.CHECK_INTERVAL_SECONDS,
        },
        "email-delivery": {
            "task": "parking.notifications",
            "schedule": config.EMAIL_INTERVAL_SECONDS,
            "options": {"expires": config.EMAIL_INTERVAL_SECONDS - 5},
        },
        "checker-heartbeat": {
            "task": "parking.heartbeat",
            "schedule": 30.0,
            "options": {"expires": 60},
        },
    },
)


@app.task(name="parking.check_tickets", soft_time_limit=900, time_limit=960)
def check_tickets(run_id):
    from .collector import collect

    init_db()
    collect(run_id)


@app.task(name="parking.check_all")
def check_all():
    from .collector import enqueue

    init_db()
    enqueue()


@app.task(name="parking.heartbeat")
def heartbeat():
    init_db()
    with connect() as db:
        db.execute(
            "INSERT INTO app_meta(key,value) VALUES ('worker_heartbeat',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (now(),),
        )


@app.task(name="parking.notifications", soft_time_limit=240, time_limit=300)
def notifications():
    from .notifications import queue_monthly_reports, deliver_pending

    init_db()
    queue_monthly_reports()
    deliver_pending()
