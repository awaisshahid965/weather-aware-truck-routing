"""What the services need from the outside world, as `typing.Protocol` classes.

Ports speak in domain types and raise typed errors. They never expose a
provider's raw payloads, so a provider can be replaced without touching a
service.
"""
