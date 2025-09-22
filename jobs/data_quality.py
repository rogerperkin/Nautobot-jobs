import re

from nautobot.circuits.models import Circuit
from nautobot.dcim.models import Device, DeviceType, Location
from nautobot.extras.jobs import get_task_logger, StringVar, MultiObjectVar
from nautobot.extras.models import Role
from nautobot.apps.jobs import Job, register_jobs

logger = get_task_logger(__name__)

name = "Data Quality"


# -------------------------
# Shared Form Field Classes
# -------------------------
class FormData:
    location = MultiObjectVar(
        model=Location,
        required=False,
        description="Filter by Location"
    )
    device_role = MultiObjectVar(
        model=Role,
        required=False,
        description="Filter by Device Role"
    )
    device_type = MultiObjectVar(
        model=DeviceType,
        required=False,
        description="Filter by Device Type"
    )


# -------------------------
# Utility Functions
# -------------------------
def normalize(query_set):
    """Returns a list of names or other identifiers for logging."""
    list_of_labels = []

    for element in query_set:
        if hasattr(element, "name"):
            list_of_labels.append(element.name)
        elif hasattr(element, "model"):
            list_of_labels.append(element.model)
        elif hasattr(element, "id"):
            list_of_labels.append(str(element.id))
        else:
            list_of_labels.append(str(element))  # Fallback

    return ', '.join(list_of_labels)


def filter_devices(location=None, device_role=None, device_type=None):
    """Returns a filtered queryset of devices."""
    devices = Device.objects.all()

    if location:
        logger.debug("Filter locations: %s", normalize(location))
        devices = devices.filter(location__in=location)

    if device_role:
        logger.debug("Filter device roles: %s", normalize(device_role))
        devices = devices.filter(role__in=device_role)

    if device_type:
        logger.debug("Filter device types: %s", normalize(device_type))
        devices = devices.filter(device_type__in=device_type)

    return devices


# -------------------------
# Jobs
# -------------------------

class VerifyManagementIP(Job):
    """Verify that a device has a management IP assigned"""

    class Meta:
        name = "Verify Management IP"
        description = "Verify that a device has a management IP assigned"

    location = FormData.location
    device_role = FormData.device_role
    device_type = FormData.device_type

    def run(self, location, device_role, device_type):
        devices = filter_devices(location, device_role, device_type)

        for device in devices:
            if device.primary_ip:
                logger.info("Management IP is defined: %s", device.primary_ip, extra={"obj": device})
            else:
                logger.warning("Management IP is NOT defined on device: %s", device.name, extra={"obj": device})


class VerifyHostnames(Job):
    """Verify device hostnames match corporate standards."""

    class Meta:
        name = "Verify Hostnames"
        description = "Verify device hostnames match corporate standards"

    location = FormData.location
    device_role = FormData.device_role
    device_type = FormData.device_type

    hostname_regex = StringVar(
        description="Regular expression to check the hostname against",
        default=".*",
        required=True
    )

    def run(self, location, device_role, device_type, hostname_regex):
        logger.info("Using the regular expression: %s", hostname_regex)

        for device in filter_devices(location, device_role, device_type):
            if re.search(hostname_regex, device.name):
                logger.info("Hostname is compliant.", extra={"obj": device})
            else:
                logger.warning("Hostname is NOT compliant: %s", device.name, extra={"obj": device})


class VerifyPrimaryIP(Job):
    """Verify a device has a primary IP defined."""

    class Meta:
        name = "Verify Primary IP"
        description = "Verify a device has a primary IP defined"

    location = FormData.location
    device_role = FormData.device_role
    device_type = FormData.device_type

    def run(self, location, device_role, device_type):
        for device in filter_devices(location, device_role, device_type):

            # Skip if part of a virtual chassis and not master
            if device.virtual_chassis and device.virtual_chassis.master_id != device.id:
                continue

            if device.primary_ip:
                logger.info("Primary IP is defined (%s)", device.primary_ip, extra={"obj": device})
            else:
                logger.warning("No primary IP is defined on device: %s", device.name, extra={"obj": device})


class VerifyHasRack(Job):
    """Verify that a device is inside a rack."""

    class Meta:
        name = "Verify Device Rack"
        description = "Verify a device is inside a rack"

    location = FormData.location
    device_role = FormData.device_role
    device_type = FormData.device_type

    def run(self, location, device_role, device_type):
        for device in filter_devices(location, device_role, device_type):
            if device.rack:
                logger.info("Device is in rack: %s", device.rack, extra={"obj": device})
            else:
                logger.warning("Device is NOT in a rack: %s", device.name, extra={"obj": device})


# -------------------------
# Register All Jobs
# -------------------------
register_jobs(
    VerifyHostnames,
    VerifyPrimaryIP,
    VerifyHasRack,
    VerifyManagementIP
)
