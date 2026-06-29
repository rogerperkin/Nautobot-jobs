```python
from nautobot.apps.jobs import Job
from netmiko import ConnectHandler
import os


class JunosInterfaceStatus(Job):
    """
    Display the operational status of a Junos interface.

    Intended to be run from an Interface Object Action.
    """

    class Meta:
        name = "Show Junos Interface Status"
        description = "Retrieve interface status directly from a Junos device."

    def run(self, obj, **kwargs):
        """
        obj will be the Interface object when launched from
        an Interface Object Action.
        """

        interface = obj
        device = interface.device

        self.logger.info(f"Interface: {interface.name}")
        self.logger.info(f"Device: {device.name}")

        #
        # Validate device
        #
        if not device.platform:
            raise ValueError(f"{device.name} has no platform assigned.")

        platform = device.platform.name.lower()

        if "junos" not in platform:
            raise ValueError(
                f"{device.name} is not a Junos device "
                f"(Platform: {device.platform.name})"
            )

        #
        # Device status
        #
        if device.status.slug != "active":
            raise ValueError(
                f"{device.name} is not Active "
                f"(Status: {device.status.name})"
            )

        #
        # Primary IP
        #
        primary_ip = device.primary_ip4 or device.primary_ip6

        if primary_ip is None:
            raise ValueError(
                f"{device.name} has no Primary IP configured."
            )

        host = str(primary_ip).split("/")[0]

        #
        # Credentials
        #
        username = os.getenv("JUNOS_USERNAME")
        password = os.getenv("JUNOS_PASSWORD")

        if not username or not password:
            raise ValueError(
                "JUNOS_USERNAME or JUNOS_PASSWORD environment variables "
                "are not set."
            )

        device_params = {
            "device_type": "juniper_junos",
            "host": host,
            "username": username,
            "password": password,
            "timeout": 30,
            "fast_cli": False,
        }

        terse_command = f"show interfaces {interface.name} terse"
        detail_command = f"show interfaces {interface.name}"

        self.logger.info(f"Connecting to {device.name} ({host})")

        try:
            with ConnectHandler(**device_params) as conn:
                terse_output = conn.send_command(terse_command)
                detail_output = conn.send_command(detail_command)

        except Exception as exc:
            self.logger.error(str(exc))
            raise

        admin, link, protocol = self.parse_terse(
            terse_output,
            interface.name,
        )

        self.logger.info("")
        self.logger.info("===== Interface Status =====")
        self.logger.info(f"Interface : {interface.name}")
        self.logger.info(f"Admin     : {admin}")
        self.logger.info(f"Link      : {link}")
        self.logger.info(f"Protocol  : {protocol}")
        self.logger.info("============================")
        self.logger.info("")

        self.logger.info("===== show interfaces terse =====")
        self.logger.info(terse_output)

        self.logger.info("===== show interfaces =====")
        self.logger.info(detail_output)

        return {
            "device": device.name,
            "interface": interface.name,
            "admin": admin,
            "link": link,
            "protocol": protocol,
        }

    @staticmethod
    def parse_terse(output, interface_name):
        """
        Parse the output of:
            show interfaces <interface> terse
        """

        for line in output.splitlines():
            parts = line.split()

            if not parts:
                continue

            if (
                parts[0] == interface_name
                or parts[0].startswith(f"{interface_name}.")
            ):
                admin = parts[1] if len(parts) > 1 else "unknown"
                link = parts[2] if len(parts) > 2 else "unknown"
                protocol = parts[3] if len(parts) > 3 else "unknown"

                return admin, link, protocol

        return "unknown", "unknown", "unknown"
