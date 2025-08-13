from nautobot.extras.jobs import Job
from nautobot.dcim.models import Device

from nautobot.apps.jobs import Job, register_jobs
import re

class JunosInterfaceStatusJob(Job):
    class Meta:
        name = "Junos Interface Status"
        description = "Check interface admin/link/protocol status on a Junos device."

    device_name = "vJunos-SW-1"  # Example device, you can make this a job field
    interface_name = "ge-0/0/3"

    def run(self, data, commit):
        device = Device.objects.get(name=self.device_name)

        # Run commands
        terse_output = self._get_interface_status(device, self.interface_name)
        detail_output = self._get_interface_detail(device, self.interface_name)

        if not terse_output:
            self.log_failure(f"No output for {self.interface_name} on {device.name}")
            return

        admin, link, proto = self._parse_status_from_terse(terse_output, self.interface_name)

        # Build report
        report_html = self._format_output(
            device.name,
            self.interface_name,
            admin,
            link,
            proto,
            terse_output,
            detail_output
        )

        # Log the HTML (Nautobot will render or show it in logs, but not escape like return value)
        self.log_info(report_html)

        # Final success log
        self.log_success(f"Interface status check completed for {device.name} {self.interface_name}")

    def _get_interface_status(self, device, iface):
        return device.primary_ip.address if device.primary_ip else ""

    def _get_interface_detail(self, device, iface):
        return "Sample detailed output from Junos"

    def _parse_status_from_terse(self, terse_output, iface):
        admin, link, proto = "UNKNOWN", "UNKNOWN", "UNKNOWN"
        for line in terse_output.splitlines():
            parts = line.split()
            if parts and parts[0] == iface:
                admin = parts[1].upper()
                link = parts[2].upper()
                if len(parts) > 3:
                    proto = parts[3].upper()
                break
        return admin, link, proto

    def _format_output(self, device_name, iface, admin, link, proto, terse_output, detail_output):
        def colorize(status, text):
            colors = {
                "UP": '<span style="color:green; font-weight:bold;">',
                "DOWN": '<span style="color:red; font-weight:bold;">',
                "UNKNOWN": '<span style="color:orange; font-weight:bold;">'
            }
            end_span = "</span>"
            return f"{colors.get(status, '')}{text}{end_span}"

        return f"""
================================================================================
INTERFACE STATUS REPORT
Device: {device_name}
Interface: {iface}
================================================================================
🔧 Admin Status:     {colorize(admin, admin + " ✅" if admin == "UP" else admin + " ❌")}
📡 Link Status:      {colorize(link, link + " ✅" if link == "UP" else link + " ❌")}
🔄 Protocol Status:  {colorize(proto, proto + " ✅" if proto == "UP" else proto + " ❓")}
================================================================================
RAW CLI OUTPUTS
================================================================================
<b>$ show interfaces {iface} terse</b>
{terse_output}

<b>$ show interfaces {iface}</b>
{detail_output}
================================================================================
"""

register_jobs(JunosInterfaceStatusJob)