from nautobot.apps.jobs import Job, register_jobs, StringVar
from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from netmiko import ConnectHandler
import os


class JunosInterfaceStatusJob(Job):
    """
    Async job to fetch Junos interface status
    """

    interface_name = StringVar(
        description="Interface name (e.g. ge-0/0/0)",
        default="ge-0/0/0"
    )

    class Meta:
        name = "Junos Interface Status Job"
        description = "Fetch interface status from a Junos device"

    def run(self, device, interface_name, **kwargs):
        self.logger.info(f"Running job for device {device.name}")

        # ✅ Platform check
        platform_name = (device.platform.name or "").lower() if device.platform else ""
        if "junos" not in platform_name:
            raise ValueError(f"{device.name} is not a Junos device")

        # ✅ Status check (safe for Nautobot 3)
        if device.status.name != "Active":
            raise ValueError(f"{device.name} is not Active")

        # ✅ IP check
        if not (device.primary_ip4 or device.primary_ip6):
            raise ValueError(f"{device.name} has no primary IP")

        device_ip = str(device.primary_ip4 or device.primary_ip6).split("/")[0]

        # ✅ Credentials (replace with Secrets ideally)
        creds = {
            "device_type": "juniper_junos",
            "host": device_ip,
            "username": os.getenv("JUNOS_USERNAME"),
            "password": os.getenv("JUNOS_PASSWORD"),
            "timeout": 30,
        }

        terse_cmd = f"show interfaces {interface_name} terse"
        detail_cmd = f"show interfaces {interface_name}"

        self.logger.info("Connecting to device...")

        with ConnectHandler(**creds) as conn:
            terse_output = conn.send_command(terse_cmd)
            detail_output = conn.send_command(detail_cmd)

        admin, link, proto = self.parse_terse(terse_output, interface_name)

        self.logger.info(
            f"{device.name} {interface_name} -> "
            f"Admin={admin}, Link={link}, Proto={proto}"
        )

        self.logger.info("---- RAW OUTPUT ----")
        self.logger.info(terse_output)
        self.logger.info(detail_output)

    def parse_terse(self, output, iface):
        for line in output.splitlines():
            parts = line.split()
            if parts and parts[0].startswith(iface):
                admin = parts[1] if len(parts) > 1 else "unknown"
                link = parts[2] if len(parts) > 2 else "unknown"
                proto = parts[3] if len(parts) > 3 else "unknown"
                return admin, link, proto
        return "unknown", "unknown", "unknown"


register_jobs(JunosInterfaceStatusJob)