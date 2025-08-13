from nautobot.extras.jobs import Job, StringVar, ObjectVar
from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from netmiko import ConnectHandler
from nautobot.apps.jobs import register_jobs
import os

class JunosInterfaceStatusJob(Job):
    class Meta:
        name = "Show Junos Interface Status"
        description = "Display interface status for a Junos device (plain text)"
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
        self.log(level="failure", message=f"Device {device.name} is not a Junos device")
        return

    active_status = Status.objects.get(name="Active")
    if device.status != active_status:
        self.log(level="failure", message=f"Device {device.name} is not in Active status")
        return

    if not (device.primary_ip4 or device.primary_ip6):
        self.log(level="failure", message=f"Device {device.name} has no primary IP address")
        return

    device_ip = str(device.primary_ip4 or device.primary_ip6).split('/')[0]

    try:
        output = self._get_interface_status(device_ip, interface_name)
        if not output or not output.get("main_output"):
            self.log(level="warning", message=f"No output for interface {interface_name} on {device.name}")
            return

        admin, link, proto = self._parse_status_from_terse(output["main_output"], interface_name)
        report = self._format_plain_output(device.name, interface_name, admin, link, proto, output)
        self.log(level="info", message=report)

    except Exception as e:
        self.log(level="failure", message=f"Error retrieving interface status: {e}")


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

    def _format_plain_output(self, device_name, interface_name, admin, link, proto, output):
        lines = [
            "="*50,
            "INTERFACE STATUS REPORT",
            f"Device: {device_name}",
            f"Interface: {interface_name}",
            "="*50,
            f"Admin Status:     {admin.upper()}",
            f"Link Status:      {link.upper()}",
            f"Protocol Status:  {proto.upper()}",
            "-"*50,
            f"$ {output['terse_command']}",
            output["main_output"],
            f"$ {output['detailed_command']}",
            output["detailed_output"],
            "="*50,
        ]
        return "\n".join(lines)

register_jobs(JunosInterfaceStatusJob)
