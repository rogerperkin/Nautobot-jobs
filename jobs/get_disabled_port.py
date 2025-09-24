from nautobot.extras.jobs import Job, ObjectVar, ChoiceVar
from nautobot.dcim.models import Device
from netmiko import ConnectHandler
from nautobot.apps.jobs import Job, register_jobs
import json


class NokiaInterfaceSelector(Job):
    device = ObjectVar(model=Device, description="Select a Nokia SR OS device")
    interface = ChoiceVar(choices="interface_choices", description="Select a disabled 100G interface to enable")

    class Meta:
        name = "Enable Admin-Down 100G Port"
        description = "Connect to a Nokia SR OS device via SSH, list admin-down 100G ports, and enable one."
        group = "Nokia Automation"

    def interface_choices(self):
        if not hasattr(self, "data") or "device" not in self.data or not self.data["device"]:
            return []

        device = self.data["device"]
        host = device.primary_ip.address.split("/")[0] if device.primary_ip else None
        if not host:
            self.log_failure("Device has no primary IP")
            return []

        secrets = get_secrets_for_object(device)
        username = secrets.get("SSH", {}).get("Username")
        password = secrets.get("SSH", {}).get("Password")
        if not username or not password:
            self.log_failure("Missing SSH credentials in secrets")
            return []

        device_params = {
            "device_type": "nokia_sros",
            "host": host,
            "username": username,
            "password": password,
        }

        try:
            net_connect = ConnectHandler(**device_params)
            output = net_connect.send_command("show port detail | display json")
            port_data = json.loads(output)
            ports = self.parse_ports(port_data)
            return ports

        except Exception as e:
            self.log_failure(f"Error connecting to device: {e}")
            return []

    def parse_ports(self, port_data):
        ports = []
        try:
            port_list = port_data.get("port", [])
            for port in port_list:
                port_name = port.get("port-id")
                admin_state = port.get("admin-state")  # Adjusted - check JSON keys carefully!
                speed = port.get("ethernet", {}).get("rate", None)

                if self.is_valid_port(port_name, admin_state, speed):
                    ports.append((port_name, port_name))

        except Exception as e:
            self.log_warning(f"Failed to parse port data: {e}")
        return ports

    def is_valid_port(self, name, admin_state, speed):
        if not name:
            return False
        if speed != "rate-100g":
            return False
        if not admin_state or admin_state.lower() != "down":  # Confirm exact key & values from your JSON!
            return False
        if "lag" in name.lower() or "mgmt" in name.lower():
            return False
        return True

    def run(self, data, commit):
        device = data["device"]
        selected_interface = data["interface"]

        host = device.primary_ip.address.split("/")[0] if device.primary_ip else None
        secrets = get_secrets_for_object(device)
        username = secrets.get("SSH", {}).get("Username")
        password = secrets.get("SSH", {}).get("Password")

        device_params = {
            "device_type": "nokia_sros",
            "host": host,
            "username": username,
            "password": password,
        }

        try:
            net_connect = ConnectHandler(**device_params)

            cmd = f"configure port {selected_interface} no shutdown"
            if commit:
                net_connect.send_config_set([cmd])
                self.log_success(f"Enabled interface {selected_interface} on device {device.name}")
            else:
                self.log_info(f"[Dry-run] Would enable interface {selected_interface} on {device.name}")

        except Exception as e:
            self.log_failure(f"Failed to enable interface: {e}")


# -------------------------
# Register All Jobs
# -------------------------
register_jobs(
    NokiaInterfaceSelector
)
