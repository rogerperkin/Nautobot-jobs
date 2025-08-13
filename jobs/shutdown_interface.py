from nautobot.extras.jobs import Job, ObjectVar
from nautobot.dcim.models import Device, Interface

class ShutInterface(Job):
    """Shut down a selected interface on a selected device."""

    device = ObjectVar(model=Device, description="Select a device")
    interface = ObjectVar(model=Interface, description="Select an interface")

    class Meta:
        name = "Shutdown Interface"
        description = "Disable a selected interface on a device"

    def run(self, data, commit):
        device = data["device"]
        interface = data["interface"]

        if interface.device != device:
            self.logger.error(f"Interface {interface.name} does not belong to {device.name}.")
            return f"Error: Interface {interface.name} does not belong to device {device.name}"

        if interface.enabled:
            interface.enabled = False
            interface.save()
            self.logger.info(f"Disabled interface {interface.name} on {device.name}")
            return f"Interface {interface.name} has been shut down."
        else:
            self.logger.info(f"Interface {interface.name} on {device.name} is already shut down.")
            return f"Interface {interface.name} is already disabled."

jobs = [ShutInterface]