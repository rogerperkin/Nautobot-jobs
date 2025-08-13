from nautobot.apps.jobs import Job, register_jobs

class HelloWorldJob(Job):
    class Meta:
        name = "Hello World Job"
        description = "A simple test job that just says hello."

    def run(self):
        self.logger.info("Hello, Nautobot!")
        return "Hello, Nautobot! Job ran successfully."
    
register_jobs(
    HelloWorldJob,
)