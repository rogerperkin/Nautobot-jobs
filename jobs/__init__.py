from nautobot.core.celery import register_jobs
#from .shutdown_interface import JunosDisableInterface
from .hello_world import HelloWorldJob

register_jobs(HelloWorldJob)


