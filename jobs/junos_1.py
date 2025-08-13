from nautobot.extras.jobs import Job, StringVar, ObjectVar
from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from netmiko import ConnectHandler
from nautobot.apps.jobs import register_jobs
import logging

logger = logging.getLogger(__name__)

class JunosInterfaceStatusJob(Job):
    """
    Job to check the status of a specific interface on a Junos device.
    """

    class Meta:
        name = "Show Junos Interface Status"
        description = "Display detailed status information for a specific interface on a Junos device"
        has_sensitive_variables = False

    device = ObjectVar(
        model=Device,
        required=True,
        description="Select the Junos device"
    )

    interface_name = StringVar(
        required=True,
        description="Interface name (e.g., ge-0/0/1, xe-0/0/0, et-0/0/0)"
    )

    def run(self, device, interface_name):
        """Main job execution method."""

        # Validate device platform
        platform_name = getattr(device.platform, "name", "").lower() if device.platform else ""
        if "junos" not in platform_name:
            self.logger.error(f"Device {device.name} is not a Junos device")
            return f"ERROR: Device {device.name} is not a Junos device"

        # Check if device is reachable/active
        active_status = Status.objects.get(name="Active")
        if device.status != active_status:
            self.logger.error(f"Device {device.name} is not in Active status")
            return f"ERROR: Device {device.name} is not in Active status"

        # Check if device has primary IP
        if not (device.primary_ip4 or device.primary_ip6):
            self.logger.error(f"Device {device.name} has no primary IP address configured")
            return f"ERROR: Device {device.name} has no primary IP address configured"

        # Get device IP (prefer IPv4)
        device_ip = str(device.primary_ip4).split('/')[0] if device.primary_ip4 else str(device.primary_ip6).split('/')[0]

        try:
            # Connect to device and get interface status
            output = self._get_interface_status(device_ip, interface_name)

            if not output or not output.get('main_output'):
                return f"No output received for interface {interface_name} on {device.name}"

            # Format the output for better readability
            formatted_output = self._format_output(output, device, interface_name)

            self.logger.info(f"Successfully retrieved status for interface {interface_name} on {device.name}")

            return formatted_output

        except Exception as e:
            error_msg = f"Error retrieving interface status: {str(e)}"
            self.logger.error(error_msg)
            return f"ERROR: {error_msg}"

    def _get_interface_status(self, device_ip, interface_name):
        """Connect to device and retrieve interface status."""

        # Device connection parameters - replace with your secure handling!
        device_connection = {
            'device_type': 'juniper_junos',
            'host': device_ip,
            'username': 'admin',  # ideally use env vars or secrets management
            'password': 'admin@123',
            'timeout': 30,
            'session_log': 'netmiko_session.log'  # Optional: for debugging
        }

        # Generate the appropriate show command
        command = f"show interfaces {interface_name} terse"

        self.logger.info(f"Executing command: {command}")

        # Connect and execute command
        with ConnectHandler(**device_connection) as net_connect:
            # Send the show command
            output = net_connect.send_command(command)

            # Also get detailed interface information
            basic_info = net_connect.send_command(f"show interfaces {interface_name}")

            return {
                'main_output': output,
                'basic_info': basic_info,
                'command': command
            }

    def _parse_status_from_terse(self, output):
        """
        Parses the terse output to extract Admin, Link, and Proto status.
        Expected format:

        Interface               Admin Link Proto    Local                 Remote
        ge-0/0/0                up    up   up
        ge-0/0/0.16386          up    up   up

        Returns (admin, link, proto) of the first interface line, or Unknown.
        """
        lines = output.strip().splitlines()
        if len(lines) < 2:
            return "Unknown", "Unknown", "Unknown"
        
        # Find the header line (assumed first line) and interface lines after
        # We skip the header line and look at the first interface line
        # Split by whitespace, expecting at least 4 columns: Interface Admin Link Proto
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 4:
                admin = parts[1]
                link = parts[2]
                proto = parts[3]
                return admin, link, proto

        return "Unknown", "Unknown", "Unknown"

    def _format_output(self, output_dict, device, interface_name):
        """Format the command output for better readability with parsed statuses."""

        sep = "=" * 80
        sub_sep = "-" * 40

        main_output = output_dict.get('main_output', '')
        basic_info = output_dict.get('basic_info', '')

        admin, link, proto = self._parse_status_from_terse(main_output.lower())

        result = [
            sep,
            "INTERFACE STATUS REPORT",
            f"Device: {device.name}",
            f"Interface: {interface_name}",
            f"Command Executed: {output_dict.get('command', '')}",
            sep,
            "",
            "RAW INTERFACE STATUS OUTPUT:",
            sub_sep,
            main_output.strip() if main_output else "(No output)",
            "",
            "RAW ADDITIONAL INTERFACE INFORMATION:",
            sub_sep,
            basic_info.strip() if basic_info else "(No additional info)",
            "",
            "SUMMARY:",
            sub_sep,
            f"✓ Administrative Status     {admin.upper()}",
            f"✓ Physical Link             {link.upper()}",
            f"✓ Protocol Status           {proto.upper()}",
            "",
            sep,
        ]

        return "\n".join(result)


# Register the job so Nautobot can use it
register_jobs(JunosInterfaceStatusJob)
