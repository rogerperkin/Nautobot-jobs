from nautobot.apps.jobs import Job, register_jobs

name = "Hello World Jobs"

class HelloWorldJob(Job):
    class Meta:
        name = "Hello World Job"
        description = "A simple test job that just says hello."

    def run(self):
        self.logger.info("Hello, Nautobot!")
        return "Hello, Nautobot! Job ran successfully."
    
class HelloJobsWithLogs(Job):

    class Meta:
        name = "Hello Jobs with Logs"
        description = "Hello Jobs with different log types"

    def run(self):
        self.logger.info("This is an info type log.")
        self.logger.debug("This is a debug type log.")
        self.logger.warning("This is a warning type log.")
        self.logger.error("This is an error type log.")
        self.logger.critical("This is a critical type log.")
    
register_jobs(
    HelloWorldJob,
    HelloJobsWithLogs
)