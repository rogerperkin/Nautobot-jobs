from nautobot.extras.jobs import Job, StringVar, ObjectVar
from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from netmiko import ConnectHandler
from nautobot.apps.jobs import Job, register_jobs
import logging
import os

logger = logging.getLogger(__name__)

class JunosInterfaceStatusJob(Job):
    class Meta:
        name = "Show Junos Interface Status"
        description = "Display interface status for a Junos device"
        has_sensitive_variables = False

    device = ObjectVar(
        model=Device,
        required=True,
        description="Select the Junos device"
    )

    interface_name = StringVar(
        required=True,
        description="Interface name (e.g., ge-0/0/0)"
    )

    def run(self, device, interface_name):
        platform_name = getattr(device.platform, "name", "").lower() if device.platform else ""
        if "junos" not in platform_name:
            self.logger.error(f"Device {device.name} is not a Junos device")
            return f"ERROR: Device {device.name} is not a Junos device"

        active_status = Status.objects.get(name="Active")
        if device.status != active_status:
            self.logger.error(f"Device {device.name} is not in Active status")
            return f"ERROR: Device {device.name} is not in Active status"

        if not (device.primary_ip4 or device.primary_ip6):
            self.logger.error(f"Device {device.name} has no primary IP address")
            return f"ERROR: Device {device.name} has no primary IP address"

        device_ip = str(device.primary_ip4 or device.primary_ip6).split('/')[0]

        try:
            output = self._get_interface_status(device_ip, interface_name)

            if not output:
                return f"No output received for interface {interface_name} on {device.name}"

            # Parse terse output for status summary
            admin, link, proto = self._parse_status_from_terse(output["main_output"], interface_name)

            # Add summary log
            self.logger.info(
                f"Interface {interface_name} on {device.name} is {link.upper()} (Admin: {admin.upper()}, Link: {link.upper()}, Proto: {proto.upper()})"
            )

            # Format final output
            return self._format_output(device.name, interface_name, output, admin, link, proto)

        except Exception as e:
            error_msg = f"Error retrieving interface status: {str(e)}"
            self.logger.error(error_msg)
            return f"ERROR: {error_msg}"

    def _get_interface_status(self, device_ip, interface_name):
        creds = {
            'device_type': 'juniper_junos',
            'host': device_ip,
            'username': os.getenv('JUNOS_USERNAME', 'admin'),
            'password': os.getenv('JUNOS_PASSWORD', 'admin@123'),
            'timeout': 30,
        }

        command = f"show interfaces {interface_name} terse"

        self.logger.info(f"Executing command: {command}")

        with ConnectHandler(**creds) as net_connect:
            main_output = net_connect.send_command(command)
            detailed_output = net_connect.send_command(f"show interfaces {interface_name}")
            return {
                "main_output": main_output,
                "detailed_output": detailed_output,
                "command": command
            }

    def _parse_status_from_terse(self, output, iface):
        lines = output.strip().splitlines()
        for line in lines:
            if line.startswith(iface):
                parts = line.split()
                admin = parts[1] if len(parts) > 1 else "unknown"
                link = parts[2] if len(parts) > 2 else "unknown"
                proto = parts[3] if len(parts) > 3 else "unknown"
                return admin, link, proto
        return "unknown", "unknown", "unknown"

    def _format_output(self, device_name, interface_name, admin, link, proto):
        def status_icon(value):
            if value.lower() == "up":
                return "✅"
            elif value.lower() == "down":
                return "❌"
            else:
                return "❓"

        result = []
        result.append("=" * 80)
        result.append("INTERFACE STATUS REPORT")
        result.append(f"Device: {device_name}")
        result.append(f"Interface: {interface_name}")
        result.append("=" * 80)
        result.append("")
        result.append(f"🔧 Admin Status:     {admin.upper()} {status_icon(admin)}")
        result.append(f"📡 Link Status:      {link.upper()} {status_icon(link)}")
        result.append(f"🔄 Protocol Status:  {proto.upper()} {status_icon(proto)}")
        result.append("")
        result.append("=" * 80)

        return "\n".join(result)




register_jobs(JunosInterfaceStatusJob)
