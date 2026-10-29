from typing import Any

from System.Management.Automation.Host import PSHost

class RunspaceFactory:
    @staticmethod
    def CreateRunspace(host: PSHost) -> Any: ...
