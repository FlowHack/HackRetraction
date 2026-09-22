class base: pass
class plugin:
    def __call__(self, cls): return cls
    def __init__(self, *a, **k): pass
class ExecutionResult:
    @staticmethod
    def success(m): return m
    @staticmethod
    def failure(*a): return a
class PluginResult:
    RecoverableError = 0
host = type("host", (), {})
