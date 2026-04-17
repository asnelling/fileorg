from __future__ import annotations

from fileorg.plugins.base import CluePlugin


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: list[CluePlugin] = []

    def register(self, plugin: CluePlugin) -> None:
        self._plugins.append(plugin)

    def all(self) -> list[CluePlugin]:
        return list(self._plugins)

    def enabled(self, names: list[str] | None = None) -> list[CluePlugin]:
        if not names:
            return list(self._plugins)
        return [p for p in self._plugins if p.name in names]


def build_default_registry(enabled_names: list[str] | None = None) -> PluginRegistry:
    from fileorg.plugins.filename import FilenamePlugin
    from fileorg.plugins.exif import ExifPlugin
    from fileorg.plugins.archive import ArchivePlugin
    from fileorg.plugins.ocr import OcrPlugin
    from fileorg.plugins.encryption import EncryptionPlugin

    registry = PluginRegistry()
    for plugin in [FilenamePlugin(), ExifPlugin(), ArchivePlugin(), OcrPlugin(), EncryptionPlugin()]:
        if enabled_names is None or plugin.name in enabled_names:
            registry.register(plugin)
    return registry
