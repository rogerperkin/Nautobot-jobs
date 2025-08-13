from nautobot.extras.jobs import Job, StringVar, ObjectVar
from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from netmiko import ConnectHandler
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

    def run(self):
        """Main job execution method."""
        
        # Validate device platform
        if not self.device.platform or "junos" not in self.device.platform.slug.lower():
            self.logger.error(f"Device {self.device.name} is not a Junos device")
            return f"ERROR: Device {self.device.name} is not a Junos device"
        
        # Check if device is reachable/active
        active_status = Status.objects.get(name="Active")
        if self.device.status != active_status:
            self.logger.error(f"Device {self.device.name} is not in Active status")
            return f"ERROR: Device {self.device.name} is not in Active status"
        
        # Check if device has primary IP
        if not (self.device.primary_ip4 or self.device.primary_ip6):
            self.logger.error(f"Device {self.device.name} has no primary IP address configured")
            return f"ERROR: Device {self.device.name} has no primary IP address configured"
        
        # Get device IP
        device_ip = str(self.device.primary_ip4 or self.device.primary_ip6).split('/')[0]
        
        try:
            # Connect to device and get interface status
            output = self._get_interface_status(device_ip)
            
            if not output:
                return f"No output received for interface {self.interface_name} on {self.device.name}"
            
            # Format the output for better readability
            formatted_output = self._format_output(output)
            
            self.logger.info(f"Successfully retrieved status for interface {self.interface_name} on {self.device.name}")
            
            return formatted_output
            
        except Exception as e:
            error_msg = f"Error retrieving interface status: {str(e)}"
            self.logger.error(error_msg)
            return f"ERROR: {error_msg}"
    
    def _get_interface_status(self, device_ip):
        """Connect to device and retrieve interface status."""
        
        # Device connection parameters
        device_connection = {
            'device_type': 'juniper_junos',
            'host': device_ip,
            'username': 'your_username',  # Configure via environment variables or secrets
            'password': 'your_password',  # Configure via environment variables or secrets
            'timeout': 30,
            'session_log': 'netmiko_session.log'  # Optional: for debugging
        }
        
        # Generate the appropriate show command
        command = self._generate_show_command()
        
        self.logger.info(f"Executing command: {command}")
        
        # Connect and execute command
        with ConnectHandler(**device_connection) as net_connect:
            # Send the show command
            output = net_connect.send_command(command)
            
            # Also get basic interface information
            basic_info = net_connect.send_command(f"show interfaces {self.interface_name}")
            
            return {
                'main_output': output,
                'basic_info': basic_info,
                'command': command
            }
    
    def _generate_show_command(self):
        """Generate the appropriate show interfaces command based on detail level."""
        
        return f"sho interfaces {self.interface_name} terse" 
    
    def _format_output(self, output_dict):
        """Format the command output for better readability."""
        
        result = []
        result.append("=" * 80)
        result.append(f"INTERFACE STATUS REPORT")
        result.append(f"Device: {self.device.name}")
        result.append(f"Interface: {self.interface_name}")
        result.append(f"Detail Level: {self.show_detail}")
        result.append(f"Command Executed: {output_dict['command']}")
        result.append("=" * 80)
        result.append("")
        
        # Add main command output
        if output_dict['main_output']:
            result.append("INTERFACE STATUS:")
            result.append("-" * 40)
            result.append(output_dict['main_output'])
            result.append("")
        
        # Add basic info if different from main output
        if (output_dict['basic_info'] and 
            output_dict['basic_info'] != output_dict['main_output'] and
            self.show_detail == "brief"):
            result.append("ADDITIONAL INTERFACE INFORMATION:")
            result.append("-" * 40)
            result.append(output_dict['basic_info'])
            result.append("")
        
        # Add summary information
        result.append("SUMMARY:")
        result.append("-" * 40)
        
        # Parse basic status information
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
        
        # Look for admin status
        if "admin down" in main_output or "administratively down" in main_output:
            result.append("! Administrative Status: DOWN (disabled)")
        else:
            result.append("✓ Administrative Status: UP (enabled)")
        
        result.append("")
        result.append("=" * 80)
        
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
    
    def _get_interface_status(self, device_ip):
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
        command = self._generate_show_command()
        
        self.logger.info(f"Executing command: {command}")
        
        # Connect and execute command
        with ConnectHandler(**device_connection) as net_connect:
            # Send the show command
            output = net_connect.send_command(command)
            
            # Also get basic interface information for brief mode
            basic_info = ""
            if self.show_detail == "brief":
                basic_info = net_connect.send_command(f"show interfaces {self.interface_name}")
            
            return {
                'main_output': output,
                'basic_info': basic_info,
                'command': command
            }

# Register both jobs
jobs = [JunosInterfaceStatusJob, JunosInterfaceStatusJobWithEnvCreds]
