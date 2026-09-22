"""Стаб orca.script для локального QA."""

from . import ExecutionResult, PluginType, PythonPluginBase


class ScriptPluginCapabilityBase(PythonPluginBase):
    """База script-капабилити (запуск через Plugins -> Run)."""

    def get_name(self) -> str:
        """Имя capability."""
        return ""

    def get_type(self) -> str:
        """Тип capability — script."""
        return PluginType.Script

    def execute(self) -> ExecutionResult:
        """Точка входа script-плагина."""
        return ExecutionResult.success()