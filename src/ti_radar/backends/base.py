"""Generic capture backend interface and factory for ti-radar."""

from __future__ import annotations


class CaptureBackend:
    name = "base"

    def prepare(self):
        """Initialize the backend. Implementations should make this repeatable."""
        pass

    def start(self, session_id, label, out_dir):
        """Start a capture run and return at least bin_path and t_radar_start_ns."""
        raise NotImplementedError

    def stop(self):
        """Stop the active capture run and return capture metadata."""
        raise NotImplementedError

    def close(self):
        """Release backend resources."""
        pass


def get_backend(name, cfg=None):
    """Return a capture backend by name."""
    cfg = cfg or {}
    name = (name or "mock").lower()
    if name == "mock":
        from ti_radar.backends.mock import MockBackend
        return MockBackend(**cfg)
    if name in ("mmwstudio", "studio", "mmwave"):
        from ti_radar.backends.studio_rstd import StudioRstdBackend
        return StudioRstdBackend(**cfg)
    if name in ("pydirect", "direct", "udp"):
        raise NotImplementedError("direct DCA capture backend has not been migrated yet")
    raise ValueError("unknown backend: %s" % name)

