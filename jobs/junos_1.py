from nautobot.extras.jobs import Job, StringVar, ObjectVar
from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from netmiko import ConnectHandler
from nautobot.apps.jobs import register_jobs
import logging
import os

logger = logging.getLogger(__name__)

# ANSI Colors for Nautobot output
ANSI_GREEN = "\033[92m"
ANSI_RED = "\033[91m"
ANSI_YELLOW = "\033[93m"
ANSI_RESET = "\033[0m"

class JunosInterfaceStatusJob(Job):
    class Meta:
        name = "Show Junos Interface Status"
        description = "Display interface status for a Junos device (colored + readable)"
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
            return self._error_block(f"Device {device.name} is not a Junos device")

        active_status = Status.objects.get(name="Active")
        if device.status != active_status:
            self.logger.error(f"Device {device.name} is not in Active status")
            return self._error_block(f"Device {device.name} is not in Active status")

        if not (device.primary_ip4 or device.primary_ip6):
            self.logger.error(f"Device {device.name} has no primary IP address")
            return self._error_block(f"Device {device.name} has no primary IP address")

        device_ip = str(device.primary_ip4 or device.primary_ip6).split('/')[0]

        try:
            output = self._get_interface_status(device_ip, interface_name)
            if not output or not output.get("main_output"):
                self.logger.warning(f"No output for interface {interface_name} on {device.name}")
                return self._error_block(f"No output for interface {interface_name} on {device.name}")

            admin, link, proto = self._parse_status_from_terse(output["main_output"], interface_name)

            # This is the “log message” you liked — will appear above the result
            self.logger.info(
                f"Interface {interface_name} on {device.name} "
                f"is {link.upper()} (Admin: {admin.upper()}, Link: {link.upper()}, Proto: {proto.upper()})"
            )

            return self._format_preformatted_output(device.name, interface_name, admin, link, proto, output)

        except Exception as e:
            error_msg = f"Error retrieving interface status: {str(e)}"
            self.logger.error(error_msg)
            return self._error_block(error_msg)

    def _get_interface_status(self, device_ip, interface_name):
        creds = {
            'device_type': 'juniper_junos',
            'host': device_ip,
            'username': os.getenv('JUNOS_USERNAME', 'admin'),
            'password': os.getenv('JUNOS_PASSWORD', 'admin@123'),
            'timeout': 30,
        }

        terse_command = f"show interfaces {interface_name} terse"
        detailed_command = f"show interfaces {interface_name}"

        with ConnectHandler(**creds) as net_connect:
            main_output = net_connect.send_command(terse_command)
            detailed_output = net_connect.send_command(detailed_command)
            return {
                "main_output": main_output,
                "detailed_output": detailed_output,
                "terse_command": terse_command,
                "detailed_command": detailed_command
            }

    def _parse_status_from_terse(self, output, iface):
        lines = output.strip().splitlines()
        for line in lines:
            if line.split()[0].startswith(iface):
                parts = line.split()
                admin = parts[1] if len(parts) > 1 else "unknown"
                link = parts[2] if len(parts) > 2 else "unknown"
                proto = parts[3] if len(parts) > 3 else "unknown"
                return admin, link, proto
        return "unknown", "unknown", "unknown"

    def _status_color(self, value):
        v = value.lower()
        if v == "up":
            return f'<span style="color:green; font-weight:bold;">{value.upper()} ✅</span>'
        elif v == "down":
            return f'<span style="color:red; font-weight:bold;">{value.upper()} ❌</span>'
        else:
            return f'<span style="color:orange; font-weight:bold;">{value.upper()} ❓</span>'
        
    def _format_preformatted_output(self, device_name, interface_name, admin, link, proto, output):
        report = []
        report.append('<div style="font-family:monospace; white-space:pre;">')
        report.append("=" * 80)
        report.append("INTERFACE STATUS REPORT")
        report.append(f"Device: {device_name}")
        report.append(f"Interface: {interface_name}")
        report.append("=" * 80)
        report.append(f"🔧 Admin Status:     {self._status_color(admin)}")
        report.append(f"📡 Link Status:      {self._status_color(link)}")
        report.append(f"🔄 Protocol Status:  {self._status_color(proto)}")
        report.append("=" * 80)
        report.append("RAW CLI OUTPUTS")
        report.append("=" * 80)
        report.append(f"<b>$ {output['terse_command']}</b>")
        report.append(output["main_output"])
        report.append("")
        report.append(f"<b>$ {output['detailed_command']}</b>")
        report.append(output["detailed_output"])
        report.append("=" * 80)
        report.append("</div>")
        return "\n".join(report)




register_jobs(JunosInterfaceStatusJob)
