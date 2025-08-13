from nautobot.extras.jobs import Job

class HelloWorldJob(Job):
    class Meta:
        name = "Hello World Job"
        description = "A simple test job that just says hello."

    def run(self):
        self.logger.info("Hello, Nautobot!")
        return "Hello, Nautobot! Job ran successfully."
