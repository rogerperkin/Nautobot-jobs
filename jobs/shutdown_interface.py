from nautobot.extras.jobs import Job, ObjectVar
from nautobot.dcim.models import Device, Interface
from netmiko import ConnectHandler
from netmiko.ssh_exception import NetmikoTimeoutException, NetmikoAuthenticationException

class JunosDisableInterface(Job):
    """
    Disable (shutdown) a specified interface on a Junos device using SSH via Netmiko.
    """

    device = ObjectVar(model=Device, description="Select a device")
    interface = ObjectVar(model=Interface, description="Select an interface")

    class Meta:
        name = "Disable Junos Interface"
        description = "SSH to Junos device and shutdown a chosen interface"

    def run(self, data, commit):
        device = data["device"]
        interface = data["interface"]

        # Verify interface belongs to device
        if interface.device != device:
            self.logger.error(f"Interface {interface.name} does not belong to device {device.name}.")
            return f"Error: Interface {interface.name} does not belong to device {device.name}"

        # Prepare connection parameters - adjust accordingly if you use secrets or custom fields
        connection_params = {
            "device_type": "juniper_junos",
            "host": device.primary_ip.address.split("/")[0],
            "username": "your_ssh_username",   # replace or pull from Nautobot secrets
            "password": "your_ssh_password",   # replace or pull from Nautobot secrets
            "timeout": 10,
        }

        try:
            self.logger.info(f"Connecting to device {device.name} at {connection_params['host']} ...")
            net_connect = ConnectHandler(**connection_params)
        except (NetmikoTimeoutException, NetmikoAuthenticationException) as e:
            self.logger.error(f"Failed to connect to {device.name}: {e}")
            return f"Connection error: {e}"

        # Build Junos CLI config commands to disable the interface
        commands = [
            f"configure",
            f"set interfaces {interface.name} disable",
            f"commit",
            f"exit"
        ]

        try:
            output = net_connect.send_config_set(commands)
            self.logger.info(f"Interface {interface.name} disabled on {device.name}.\n{output}")
            net_connect.disconnect()
            return f"Interface {interface.name} has been disabled on {device.name}."
        except Exception as e:
            self.logger.error(f"Failed to disable interface {interface.name} on {device.name}: {e}")
            return f"Error during interface shutdown: {e}"
