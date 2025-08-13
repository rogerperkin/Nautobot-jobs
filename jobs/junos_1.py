from nautobot.extras.jobs import Job, StringVar, ObjectVar
from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from netmiko import ConnectHandler
from nautobot.apps.jobs import register_jobs
import logging
import os

logger = logging.getLogger(__name__)

class JunosInterfaceStatusJob(Job):
    class Meta:
        name = "Show Junos Interface Status"
        description = "Display interface status for a Junos device (HTML formatted)"
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
            return self._error_html(f"Device <b>{device.name}</b> is not a Junos device")

        active_status = Status.objects.get(name="Active")
        if device.status != active_status:
            return self._error_html(f"Device <b>{device.name}</b> is not in Active status")

        if not (device.primary_ip4 or device.primary_ip6):
            return self._error_html(f"Device <b>{device.name}</b> has no primary IP address")

        device_ip = str(device.primary_ip4 or device.primary_ip6).split('/')[0]

        try:
            output = self._get_interface_status(device_ip, interface_name)
            if not output or not output.get("main_output"):
                return self._error_html(f"No output received for interface {interface_name} on {device.name}")

            admin, link, proto = self._parse_status_from_terse(output["main_output"], interface_name)

            return self._format_html_output(device.name, interface_name, admin, link, proto, output)

        except Exception as e:
            return self._error_html(f"Error retrieving interface status: {str(e)}")

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

    def _format_html_output(self, device_name, interface_name, admin, link, proto, output):
        def status_label(value):
            color_map = {"up": "green", "down": "red", "unknown": "gray"}
            icon_map = {"up": "✅", "down": "❌", "unknown": "❓"}
            val = value.lower()
            color = color_map.get(val, "gray")
            icon = icon_map.get(val, "❓")
            return f'<span style="color:{color}; font-weight:bold;">{value.upper()} {icon}</span>'

        html = []
        html.append("<h2>Interface Status Report</h2>")
        html.append(f"<b>Device:</b> {device_name}<br>")
        html.append(f"<b>Interface:</b> {interface_name}<br><br>")
        html.append(f"🔧 <b>Admin Status:</b> {status_label(admin)}<br>")
        html.append(f"📡 <b>Link Status:</b> {status_label(link)}<br>")
        html.append(f"🔄 <b>Protocol Status:</b> {status_label(proto)}<br><br>")
        html.append("<h3>Raw CLI Outputs</h3>")
        html.append(f"<b>$ {output['terse_command']}</b>")
        html.append(f"<pre>{output['main_output']}</pre>")
        html.append(f"<b>$ {output['detailed_command']}</b>")
        html.append(f"<pre>{output['detailed_output']}</pre>")
        return "\n".join(html)

    def _error_html(self, message):
        return f'<span style="color:red; font-weight:bold;">ERROR:</span> {message}'


register_jobs(JunosInterfaceStatusJob)
