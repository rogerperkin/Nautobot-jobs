from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from nautobot.apps.jobs import Job
from nautobot.core.jobs import ObjectVar, StringVar
from nautobot.dcim.models import Device


class GetInterfaceStatus(Job):
    device = ObjectVar(
        model=Device,
        description="Select the device to connect to.",
    )
    interface_name = StringVar(
        description="Enter the full interface/port name, e.g., 4/1/c4",
    )

    def run(self, *, device, interface_name):

        if not device.primary_ip4:
            self.log("failure", f"Device {device.name} missing primary IP")
            raise Exception("Device has no primary IPv4 address.")

        ip_address = device.primary_ip4.address.split("/")[0]

        secrets_group = device.secrets_group
        if not secrets_group:
            self.log("failure", f"Device {device.name} has no Secrets Group assigned.")
            raise Exception("Device has no Secrets Group assigned.")

        try:
            context = secrets_group.get_context()
            username = context["username"]
            password = context["password"]
        except KeyError as e:
            self.log("failure", f"Missing secret key: {e}")
            raise Exception("Secrets missing required keys.")
        except Exception as e:
            self.log("failure", f"Error retrieving secrets: {e}")
            raise Exception("Failed to retrieve device credentials.")

        connection_params = {
            "device_type": "nokia_sros",
            "host": ip_address,
            "username": username,
            "password": password,
        }

        try:
            self.log("info", f"Connecting to {device.name} at {ip_address}...")
            connection = ConnectHandler(**connection_params)

            command = f"show port {interface_name}"
            self.log("info", f"Sending command: {command}")
            output = connection.send_command(command)

            connection.disconnect()
        except NetmikoTimeoutException:
            self.log("failure", f"Connection to {device.name} timed out.")
            raise Exception("Connection timed out.")
        except NetmikoAuthenticationException:
            self.log("failure", f"Authentication failed for {device.name}.")
            raise Exception("Authentication failed.")
        except Exception as e:
            self.log("failure", f"Unexpected error: {e}")
            raise Exception("Unexpected error during connection or command.")

        admin_state = None
        port_state = None

        for line in output.splitlines():
            if interface_name in line:
                parts = line.split()
                if len(parts) >= 3:
                    admin_state = parts[1]
                    port_state = parts[2]
                break

        if admin_state and port_state:
            self.log(
                "success",
                f"Interface {interface_name} on {device.name} → Admin State: {admin_state}, Port State: {port_state}",
            )
        else:
            self.log("info", f"Could not parse interface status. Raw output:\n{output}")
