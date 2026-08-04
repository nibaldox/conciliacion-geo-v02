"""Optional memory instrumentation for the blast simulation engine.

Disabled by default. When enabled, records:
- maximum auxiliary buffer shape and bytes observed
- number of spatial and temporal blocks processed
- RSS (via stdlib ``resource`` on Linux/macOS)
- tracemalloc peak as a complementary measure

Usage:
    instr = MemoryInstrumentation(enabled=True)
    result = run_simulation(..., instrumentation=instr)
    report = instr.report()
"""
from __future__ import annotations

import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Optional


def _get_rss_bytes() -> int:
    """Return current process RSS in bytes (Linux/macOS)."""
    try:
        import resource
        # Linux: ru_maxrss is in KB; macOS: in bytes.
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        import sys
        if sys.platform.startswith("linux"):
            return rss * 1024
        return rss
    except Exception:
        return 0


@dataclass
class MemoryInstrumentation:
    """Collects memory metrics during simulation. Disabled by default."""
    enabled: bool = False
    max_spatial_buffer_elements: int = 0
    max_temporal_buffer_elements: int = 0
    max_time_bins: int = 0
    max_segments_simultaneous: int = 0
    largest_aux_shape: tuple[int, ...] = ()
    largest_aux_bytes: int = 0
    n_spatial_blocks: int = 0
    n_temporal_blocks: int = 0
    rss_basal: int = 0
    rss_max: int = 0
    tracemalloc_peak: int = 0
    _tracemalloc_started: bool = False

    def start(self) -> None:
        if not self.enabled:
            return
        self.rss_basal = _get_rss_bytes()
        self.rss_max = self.rss_basal
        tracemalloc.start()
        self._tracemalloc_started = True

    def stop(self) -> None:
        if not self.enabled:
            return
        self.rss_max = max(self.rss_max, _get_rss_bytes())
        if self._tracemalloc_started:
            _, peak = tracemalloc.get_traced_memory()
            self.tracemalloc_peak = peak
            tracemalloc.stop()
            self._tracemalloc_started = False

    def record_spatial_buffer(self, n_elements: int) -> None:
        if not self.enabled:
            return
        self.max_spatial_buffer_elements = max(
            self.max_spatial_buffer_elements, n_elements,
        )
        self.n_spatial_blocks += 1
        self.rss_max = max(self.rss_max, _get_rss_bytes())

    def record_temporal_buffer(self, n_elements: int, n_bins: int, n_segs: int) -> None:
        if not self.enabled:
            return
        self.max_temporal_buffer_elements = max(
            self.max_temporal_buffer_elements, n_elements,
        )
        self.max_time_bins = max(self.max_time_bins, n_bins)
        self.max_segments_simultaneous = max(
            self.max_segments_simultaneous, n_segs,
        )
        self.n_temporal_blocks += 1
        self.rss_max = max(self.rss_max, _get_rss_bytes())

    def record_aux(self, shape: tuple[int, ...], dtype_bytes: int = 8) -> None:
        if not self.enabled:
            return
        total = 1
        for s in shape:
            total *= max(s, 1)
        total_bytes = total * dtype_bytes
        if total_bytes > self.largest_aux_bytes:
            self.largest_aux_bytes = total_bytes
            self.largest_aux_shape = shape

    def report(self) -> dict[str, Any]:
        return {
            "max_spatial_buffer_elements": self.max_spatial_buffer_elements,
            "max_temporal_buffer_elements": self.max_temporal_buffer_elements,
            "max_time_bins": self.max_time_bins,
            "max_segments_simultaneous": self.max_segments_simultaneous,
            "largest_aux_shape": list(self.largest_aux_shape),
            "largest_aux_bytes": self.largest_aux_bytes,
            "n_spatial_blocks": self.n_spatial_blocks,
            "n_temporal_blocks": self.n_temporal_blocks,
            "rss_basal_bytes": self.rss_basal,
            "rss_max_bytes": self.rss_max,
            "rss_delta_bytes": self.rss_max - self.rss_basal,
            "tracemalloc_peak_bytes": self.tracemalloc_peak,
        }
