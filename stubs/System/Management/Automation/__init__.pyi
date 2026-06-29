from typing import Any, overload

from System.Collections.ObjectModel import Collection
from System.Management.Automation.Host import ConsoleColor as ConsoleColor
from System.Management.Automation.Host import ProgressRecordType as ProgressRecordType
from System.Security import SecureString

class PSObject:
    def __init__(self, value: Any = None) -> None: ...
    def __str__(self) -> str: ...
    @property
    def Properties(self) -> Any: ...

class InformationRecord:
    pass

class PSCredential:
    def __init__(self, user_name: str, password: SecureString) -> None: ...

class ProgressRecord:
    Activity: str
    ActivityId: int
    StatusDescription: str
    PercentComplete: int
    RecordType: ProgressRecordType

class PSCredentialTypes:
    pass

class PSCredentialUIOptions:
    pass

class Streams:
    Error: Any

class PSCommand:
    @overload
    def AddCommand(self, cmdlet: str) -> "PSCommand": ...
    @overload
    def AddCommand(self, cmdlet: str, useLocalScope: bool) -> "PSCommand": ...
    def AddScript(self, script: str) -> "PSCommand": ...
    @overload
    def AddParameter(self, parameterName: str, value: object) -> "PSCommand": ...
    @overload
    def AddParameter(self, parameterName: str) -> "PSCommand": ...
    def Clear(self) -> None: ...

class PowerShell:
    Commands: PSCommand
    Streams: Streams
    Runspace: Any
    HadErrors: bool
    @staticmethod
    def Create() -> "PowerShell": ...
    def Invoke(self, input: Any = None) -> Collection[PSObject]: ...
    def Dispose(self) -> None: ...
