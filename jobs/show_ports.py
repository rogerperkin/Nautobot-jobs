from nautobot.extras.jobs import Job, ObjectVar, ChoiceVar
from nautobot.dcim.models import Device
from netmiko import ConnectHandler
import json

class NokiaInterfaceSelector(Job):
    device = ObjectVar(model=Device, description="Select a Nokia SR OS device")

    interface = ChoiceVar(choices=[], description="Select a physical interface")

    def __init__(self):
        super().__init__()
        self._interface_choices = []

    def interface_choices(self):
        if not hasattr(self, "data") or "device" not in self.data:
            return []

        device = self.data["device"]
        host = device.primary_ip.address.split("/")[0] if device.primary_ip else None

        if not host:
            self.log_failure("Device has no primary IP")
            return []

        device_params = {
            "device_type": "nokia_sros",
            "host": host,
            "username": "admin",         # 🔐 Use Nautobot Secrets in production
            "password": "your_password", # 🔐 Don't hardcode
        }

        try:
            net_connect = ConnectHandler(**device_params)

            # Use MD-CLI with JSON output
            cmd = "show port detail | display json"
            output = net_connect.send_command(cmd)

            port_data = json.loads(output)
            ports = self.parse_ports(port_data)

            return ports

        except Exception as e:
            self.log_failure(f"Error connecting to device: {e}")
            return []

    def parse_ports(self, port_data):
        """
        Parse MD-CLI JSON to extract and filter port names.
        """
        ports = []

        # Nokia MD-CLI JSON structure can vary slightly — adjust as needed
        try:
            port_list = port_data.get("port", [])
            for port in port_list:
                port_name = port.get("port-id")
                admin_state = port.get("oper-state")
                speed = port.get("ethernet", {}).get("rate", None)

                # 🔍 Filtering logic here
                if self.is_valid_port(port_name, admin_state, speed):
                    ports.append((port_name, port_name))

        except Exception as e:
            self.log_warning(f"Failed to parse port data: {e}")

        return ports

    def is_valid_port(self, name, admin_state, speed):
        """
        Custom filter: only physical 100G ports that are admin-down
        """
        if not name:
            return False
        if speed != "rate-100g":
            return False
        if admin_state.lower() != "down":
            return False
        if "lag" in name.lower() or "mgmt" in name.lower():
            return False
        return True

    def run(self, data, commit):
        device = data["device"]
        selected_interface = data["interface"]

        self.log_success(f"Selected interface {selected_interface} on device {device.name}")
        # Optional: Push config here to admin-up the port

