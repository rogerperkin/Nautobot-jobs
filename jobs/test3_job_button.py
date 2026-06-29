from nautobot.apps.jobs import JobButtonReceiver, register_jobs
from netmiko import ConnectHandler
import os


class ShowJunosInterfaceStatus(JobButtonReceiver):
    """
    Job Button Receiver for Interface objects.

    Runs when the "Show Interface Status" button is clicked.
    """

    class Meta:
        name = "Show Junos Interface Status"
        description = "Retrieve interface status from a Junos device."

    def receive_job_button(self, obj):
        interface = obj
        device = interface.device

        self.logger.info(f"Device: {device.name}")
        self.logger.info(f"Interface: {interface.name}")

        #
        # Validate platform
        #
        if not device.platform:
            raise ValueError(f"{device.name} has no Platform assigned.")

        if "junos" not in device.platform.name.lower():
            raise ValueError(f"{device.name} is not a Junos device.")

        #
        # Validate status
        #
        if device.status.slug != "active":
            raise ValueError(f"{device.name} is not Active.")

        #
        # Validate IP
        #
        primary_ip = device.primary_ip4 or device.primary_ip6

        if primary_ip is None:
            raise ValueError(f"{device.name} has no Primary IP.")

        host = str(primary_ip).split("/")[0]

        username = os.getenv("JUNOS_USERNAME")
        password = os.getenv("JUNOS_PASSWORD")

        if not username or not password:
            raise ValueError(
                "JUNOS_USERNAME or JUNOS_PASSWORD environment variables are not set."
            )

        params = {
            "device_type": "juniper_junos",
            "host": host,
            "username": username,
            "password": password,
            "timeout": 30,
            "fast_cli": False,
        }

        terse_cmd = f"show interfaces {interface.name} terse"
        detail_cmd = f"show interfaces {interface.name}"

        self.logger.info(f"Connecting to {host}")

        with ConnectHandler(**params) as conn:
            terse = conn.send_command(terse_cmd)
            detail = conn.send_command(detail_cmd)

        admin, link, proto = self.parse_terse(terse, interface.name)

        self.logger.success("===== Interface Status =====")
        self.logger.success(f"Interface : {interface.name}")
        self.logger.success(f"Admin     : {admin}")
        self.logger.success(f"Link      : {link}")
        self.logger.success(f"Protocol  : {proto}")

        self.logger.info("")
        self.logger.info("===== show interfaces terse =====")
        self.logger.info(terse)

        self.logger.info("")
        self.logger.info("===== show interfaces =====")
        self.logger.info(detail)

    @staticmethod
    def parse_terse(output, iface):
        for line in output.splitlines():
            parts = line.split()

            if not parts:
                continue

            if parts[0] == iface or parts[0].startswith(f"{iface}."):
                admin = parts[1] if len(parts) > 1 else "unknown"
                link = parts[2] if len(parts) > 2 else "unknown"
                proto = parts[3] if len(parts) > 3 else "unknown"
                return admin, link, proto

        return "unknown", "unknown", "unknown"


register_jobs(ShowJunosInterfaceStatus)