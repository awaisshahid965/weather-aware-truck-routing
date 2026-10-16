"""Fakes shared by the adapter tests."""


class FakeClock:
    """Monotonic time that moves only when told: by `sleep`, or by a provider that is slow to fail."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
