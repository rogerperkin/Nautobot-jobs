class VerifyManagementIP(Job):
    class Meta:
        name = "Verify Management IP"
        description = "Verify that a device has a management IP assigned"

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

    def run(self, location, device_role, device_type):
        devices = Device.objects.all()
        if location:
            devices = devices.filter(location__in=location)
        if device_role:
            devices = devices.filter(role__in=device_role)
        if device_type:
            devices = devices.filter(device_type__in=device_type)

        for device in devices:
            if device.primary_ip:
                logger.info("Management IP is defined: %s", device.primary_ip, extra={"obj": device})
            else:
                logger.warning("Management IP is NOT defined on device: %s", device.name, extra={"obj": device})
