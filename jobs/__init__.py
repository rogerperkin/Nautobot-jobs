from nautobot.core.celery import register_jobs
from .shut_interface import ShutInterface

register_jobs(ShutInterface)

