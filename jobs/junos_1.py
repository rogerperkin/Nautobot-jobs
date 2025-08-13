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
        
        # Get device IP (IPv4 preferred)
        device_ip = str(device.primary_ip4).split('/')[0] if device.primary_ip4 else str(device.primary_ip6).split('/')[0]
        
        try:
            # Connect to device and get interface status
            output = self._get_interface_status(device_ip, interface_name)
            
            if not output:
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
        
        # Device connection parameters
        device_connection = {
            'device_type': 'juniper_junos',
            'host': device_ip,
            'username': 'admin',  # TODO: configure securely (env vars or secrets)
            'password': 'admin@123',  # TODO: configure securely (env vars or secrets)
            'timeout': 30,
            'session_log': 'netmiko_session.log'  # Optional: for debugging
        }
        
        # Generate the appropriate show command
        command = self._generate_show_command(interface_name)
        
        self.logger.info(f"Executing command: {command}")
        
        # Connect and execute command
        with ConnectHandler(**device_connection) as net_connect:
            # Send the show command
            output = net_connect.send_command(command)
            
            # Also get basic interface information
            basic_info = net_connect.send_command(f"show interfaces {interface_name}")
            
            return {
                'main_output': output,
                'basic_info': basic_info,
                'command': command
            }
    
    def _generate_show_command(self, interface_name):
        """Generate the appropriate show interfaces command."""
        return f"show interfaces {interface_name} terse" 
    
    def _format_output(self, output_dict, device, interface_name):
        """Format the command output for better readability."""
        
        sep = "=" * 80
        sub_sep = "-" * 40

        result = [
            sep,
            "INTERFACE STATUS REPORT",
            f"Device: {device.name}",
            f"Interface: {interface_name}",
            f"Command Executed: {output_dict['command']}",
            sep,
            "",
        ]

        main_output = output_dict['main_output'].strip() if output_dict['main_output'] else ""
        basic_info = output_dict.get('basic_info', "").strip()

        # Check if output contains an error message
        if "error:" in main_output.lower():
            result.append("ERROR RECEIVED FROM DEVICE:")
            result.append(sub_sep)
            result.append(main_output)
            result.append("")
        else:
            # Normal interface status output
            if main_output:
                result.append("INTERFACE STATUS:")
                result.append(sub_sep)
                result.append(main_output)
                result.append("")

            if basic_info and basic_info != main_output:
                result.append("ADDITIONAL INTERFACE INFORMATION:")
                result.append(sub_sep)
                result.append(basic_info)
                result.append("")

        # Summary
        result.append("SUMMARY:")
        result.append(sub_sep)

        lo = main_output.lower()

        def status_line(label, up_cond, down_cond):
            if up_cond in lo:
                return f"✓ {label:<25} UP"
            elif down_cond in lo:
                return f"✗ {label:<25} DOWN"
            else:
                return f"? {label:<25} Unknown"

        result.append(status_line("Physical Link", "physical link is up", "physical link is down"))
        result.append(status_line("Protocol Status", "protocol is up", "protocol is down"))

        if "admin down" in lo or "administratively down" in lo:
            result.append("! Administrative Status     DOWN (disabled)")
        else:
            result.append("✓ Administrative Status     UP (enabled)")

        result.append("")
        result.append(sep)

        return "\n".join(result)

# Alternative version using environment variables for credentials
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
        """Connect to device using environment variables for credentials."""
        import os
        
        username = os.getenv('JUNOS_USERNAME', 'admin')
        password = os.getenv('JUNOS_PASSWORD', '')
        
        if not password:
            raise Exception("JUNOS_PASSWORD environment variable not set")
        
        # Device connection parameters
        device_connection = {
            'device_type': 'juniper_junos',
            'host': device_ip,
            'username': username,
            'password': password,
            'timeout': 30,
        }
        
        # Generate the appropriate show command
        command = self._generate_show_command(interface_name)
        
        self.logger.info(f"Executing command: {command}")
        
        # Connect and execute command
        with ConnectHandler(**device_connection) as net_connect:
            # Send the show command
            output = net_connect.send_command(command)
            
            # Also get basic interface information for brief mode
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
