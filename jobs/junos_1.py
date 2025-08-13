from nautobot.extras.jobs import Job, StringVar, ObjectVar
from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from netmiko import ConnectHandler
from nautobot.apps.jobs import register_jobs
import logging
import os

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
        # Validate device platform
        platform_name = getattr(device.platform, "name", "").lower() if device.platform else ""
        if "junos" not in platform_name:
            self.logger.error(f"Device {device.name} is not a Junos device")
            return f"ERROR: Device {device.name} is not a Junos device"

        # Check if device is reachable/active
        try:
            active_status = Status.objects.get(name="Active")
        except Status.DoesNotExist:
            return "ERROR: 'Active' status not found in Nautobot."
        
        if device.status != active_status:
            self.logger.error(f"Device {device.name} is not in Active status")
            return f"ERROR: Device {device.name} is not in Active status"

        # Check if device has primary IP
        if not (device.primary_ip4 or device.primary_ip6):
            self.logger.error(f"Device {device.name} has no primary IP address configured")
            return f"ERROR: Device {device.name} has no primary IP address configured"

        # Get device IP (prefer IPv4 if available)
        device_ip = str(device.primary_ip4 or device.primary_ip6).split('/')[0]

        try:
            output = self._get_interface_status(device_ip, interface_name)

            if not output:
                return f"No output received for interface {interface_name} on {device.name}"

            formatted_output = self._format_output(output, device, interface_name)

            self.logger.info(f"Successfully retrieved status for interface {interface_name} on {device.name}")

            return formatted_output

        except Exception as e:
            error_msg = f"Error retrieving interface status: {str(e)}"
            self.logger.error(error_msg)
            return f"ERROR: {error_msg}"

    def _get_interface_status(self, device_ip, interface_name):
        """Connect to device and retrieve interface status."""

        device_connection = {
            'device_type': 'juniper_junos',
            'host': device_ip,
            'username': 'admin',        # Consider fetching from env variables or secrets manager
            'password': 'admin@123',    # Consider fetching from env variables or secrets manager
            'timeout': 30,
            'session_log': 'netmiko_session.log'  # Optional for debugging
        }

        command = self._generate_show_command(interface_name)
        self.logger.info(f"Executing command: {command}")

        with ConnectHandler(**device_connection) as net_connect:
            output = net_connect.send_command(command)
            basic_info = net_connect.send_command(f"show interfaces {interface_name}")

            return {
                'main_output': output,
                'basic_info': basic_info,
                'command': command
            }

    def _generate_show_command(self, interface_name):
        return f"show interfaces {interface_name} terse"

    def _format_output(self, output_dict, device, interface_name):
        result = []
        result.append("=" * 80)
        result.append("INTERFACE STATUS REPORT")
        result.append(f"Device: {device.name}")
        result.append(f"Interface: {interface_name}")
        result.append(f"Command Executed: {output_dict['command']}")
        result.append("=" * 80)
        result.append("")

        if output_dict['main_output']:
            result.append("INTERFACE STATUS:")
            result.append("-" * 40)
            result.append(output_dict['main_output'])
            result.append("")

        if output_dict['basic_info'] and output_dict['basic_info'] != output_dict['main_output']:
            result.append("ADDITIONAL INTERFACE INFORMATION:")
            result.append("-" * 40)
            result.append(output_dict['basic_info'])
            result.append("")

        result.append("SUMMARY:")
        result.append("-" * 40)

        main_output = output_dict['main_output'].lower()

        if "physical link is up" in main_output:
            result.append("✓ Physical Link: UP")
        elif "physical link is down" in main_output:
            result.append("✗ Physical Link: DOWN")
        else:
            result.append("? Physical Link: Unknown")

        if "protocol is up" in main_output:
            result.append("✓ Protocol Status: UP")
        elif "protocol is down" in main_output:
            result.append("✗ Protocol Status: DOWN")
        else:
            result.append("? Protocol Status: Unknown")

        if "admin down" in main_output or "administratively down" in main_output:
            result.append("! Administrative Status: DOWN (disabled)")
        else:
            result.append("✓ Administrative Status: UP (enabled)")

        result.append("")
        result.append("=" * 80)

        return "\n".join(result)


class JunosInterfaceStatusJobWithEnvCreds(JunosInterfaceStatusJob):
    """
    Same job but using environment variables for credentials.
    Set JUNOS_USERNAME and JUNOS_PASSWORD environment variables.
    """

    class Meta:
        name = "Show Junos Interface Status (Env Creds)"
        description = "Display interface status using environment variable credentials"
        has_sensitive_variables = False

    def _get_interface_status(self, device_ip, interface_name):
        username = os.getenv('JUNOS_USERNAME', 'admin')
        password = os.getenv('JUNOS_PASSWORD', '')

        if not password:
            raise Exception("JUNOS_PASSWORD environment variable not set")

        device_connection = {
            'device_type': 'juniper_junos',
            'host': device_ip,
            'username': username,
            'password': password,
            'timeout': 30,
        }

        command = self._generate_show_command(interface_name)
        self.logger.info(f"Executing command: {command}")

        with ConnectHandler(**device_connection) as net_connect:
            output = net_connect.send_command(command)
            basic_info = net_connect.send_command(f"show interfaces {interface_name}")

            return {
                'main_output': output,
                'basic_info': basic_info,
                'command': command
            }


register_jobs(
    JunosInterfaceStatusJob,
    JunosInterfaceStatusJobWithEnvCreds
)
