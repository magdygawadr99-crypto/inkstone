from __future__ import annotations

from dataclasses import dataclass, field

from ..utils.text import humanize_duration, pluralize


@dataclass
class BuildReport:
    """What one call to Builder.build() did."""

    pages_written: int = 0
    # pages whose output was left alone: nothing they depend on changed, or
    # the freshly rendered bytes were already on disk
    pages_skipped: int = 0
    assets_copied: int = 0
    files_removed: int = 0
    warnings: list[str] = field(default_factory=list)
    duration: float = 0.0
    phases: dict[str, float] = field(default_factory=dict)
    # every file written by this build, POSIX paths relative to the output dir
    output_paths: list[str] = field(default_factory=list)
    # pages that went through their template (a subset may not have changed)
    pages_rendered: int = 0
    # generated files other than pages and assets: feeds, sitemap, resources...
    files_written: int = 0
    removed_paths: list[str] = field(default_factory=list)
    incremental: bool = True

    @property
    def pages_total(self) -> int:
        return self.pages_written + self.pages_skipped

    @property
    def changed(self) -> bool:
        """Did anything in the output directory change?"""
        return bool(self.output_paths or self.removed_paths)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def summary(self) -> str:
        """The one line the command line prints after a build."""
        parts = [f"{pluralize(self.pages_written, 'page')} written"]
        if self.pages_skipped:
            parts.append(f"{self.pages_skipped} unchanged")
        if self.assets_copied:
            parts.append(pluralize(self.assets_copied, "asset"))
        if self.files_written:
            parts.append(f"{pluralize(self.files_written, 'other file')}")
        if self.files_removed:
            parts.append(f"{self.files_removed} removed")
        text = ", ".join(parts) + f" in {humanize_duration(self.duration)}"
        if self.warnings:
            text += f" ({pluralize(len(self.warnings), 'warning')})"
        return text

    def phase_table(self) -> str:
        """Per-phase timings for `inkstone build --profile`."""
        if not self.phases:
            return ""
        width = max(len(name) for name in self.phases)
        total = sum(self.phases.values()) or 1.0
        lines = []
        for name, seconds in self.phases.items():
            share = seconds / total
            lines.append(
                f"{name:<{width}}  {humanize_duration(seconds):>8}  {share:4.0%}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "pages_written": self.pages_written,
            "pages_skipped": self.pages_skipped,
            "pages_rendered": self.pages_rendered,
            "assets_copied": self.assets_copied,
            "files_written": self.files_written,
            "files_removed": self.files_removed,
            "warnings": list(self.warnings),
            "duration": self.duration,
            "phases": dict(self.phases),
            "output_paths": list(self.output_paths),
            "removed_paths": list(self.removed_paths),
            "incremental": self.incremental,
        }
