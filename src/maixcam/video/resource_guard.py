"""In-process exclusive ownership for MaixCam hardware resources."""


class ResourceBusyError(RuntimeError):
    """Raised when a resource is already owned by another service."""


class ResourceOwnershipError(RuntimeError):
    """Raised when a service releases a resource it does not own."""


class ResourceRegistry:
    """Track explicit resource owners within one MaixCam application process."""

    def __init__(self):
        self._owners = {}

    @staticmethod
    def _validate_name(value, field):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("%s must be a non-empty string" % field)
        return value.strip()

    def acquire(self, resource, owner):
        resource = self._validate_name(resource, "resource")
        owner = self._validate_name(owner, "owner")
        current_owner = self._owners.get(resource)
        if current_owner is not None:
            raise ResourceBusyError(
                "%s is owned by %s" % (resource, current_owner)
            )
        self._owners[resource] = owner
        return self.snapshot()

    def release(self, resource, owner):
        resource = self._validate_name(resource, "resource")
        owner = self._validate_name(owner, "owner")
        current_owner = self._owners.get(resource)
        if current_owner is None:
            return self.snapshot()
        if current_owner != owner:
            raise ResourceOwnershipError(
                "%s is owned by %s, not %s" % (resource, current_owner, owner)
            )
        del self._owners[resource]
        return self.snapshot()

    def owner_of(self, resource):
        resource = self._validate_name(resource, "resource")
        return self._owners.get(resource)

    def snapshot(self):
        return dict(self._owners)
