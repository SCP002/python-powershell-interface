from enum import IntEnum, IntFlag
from typing import Any

from System import Guid, Version
from System.Management.Automation import InformationRecord, ProgressRecord

class ConsoleColor(IntEnum):
    Black = 0
    DarkBlue = 1
    DarkGreen = 2
    DarkCyan = 3
    DarkRed = 4
    DarkMagenta = 5
    DarkYellow = 6
    Gray = 7
    DarkGray = 8
    Blue = 9
    Green = 10
    Cyan = 11
    Red = 12
    Magenta = 13
    Yellow = 14
    White = 15

class Size:
    Width: int
    Height: int
    def __init__(self, width: int, height: int) -> None: ...

class Coordinates:
    X: int
    Y: int
    def __init__(self, x: int, y: int) -> None: ...

class Rectangle:
    Left: int
    Top: int
    Right: int
    Bottom: int
    def __init__(self, left: int, top: int, right: int, bottom: int) -> None: ...

class ProgressRecordType(IntEnum):
    Processing = 0
    Completed = 1

class BufferCellType(IntEnum):
    Complete = 0
    Leading = 1
    Trailing = 2

class BufferCell:
    def __init__(
        self, character: str, foreground: ConsoleColor, background: ConsoleColor, buffer_cell_type: BufferCellType
    ) -> None: ...

class ControlKeyStates(IntFlag):
    ShiftPressed = 0x10
    LeftAltPressed = 0x02
    RightAltPressed = 0x01
    LeftCtrlPressed = 0x08
    RightCtrlPressed = 0x04
    CapsLockOn = 0x80
    NumLockOn = 0x20

class KeyInfo:
    def __init__(
        self, virtual_key_code: int, character: str, control_key_state: ControlKeyStates, key_down: bool
    ) -> None: ...

class ChoiceDescription:
    def __init__(self, label: str, help_message: str) -> None: ...
    def get_Label(self) -> str: ...

class FieldDescription:
    Name: str
    HelpMessage: str
    ParameterTypeName: str

class PromptingException(Exception):
    pass

class ReadKeyOptions(IntFlag):
    WaitOnKey = 0x01
    NoEcho = 0x02
    AllowCtrlC = 0x04
    IncludeKeyDown = 0x10
    IncludeKeyUp = 0x20

class PSHost:
    def __init__(self, ui: "PSHostUserInterface") -> None: ...
    _ui: "PSHostUserInterface"
    _name: str
    _version: Version
    _instance_id: Guid
    _debugger_enabled: bool

class PSHostUserInterface:
    @property
    def RawUI(self) -> "PSHostRawUserInterface": ...
    @property
    def SupportsVirtualTerminal(self) -> bool: ...
    def Write(self, *args: Any) -> None: ...
    def WriteLine(self, *args: Any) -> None: ...
    def WriteDebugLine(self, message: str) -> None: ...
    def WriteErrorLine(self, message: str) -> None: ...
    def WriteVerboseLine(self, message: str) -> None: ...
    def WriteWarningLine(self, message: str) -> None: ...
    def WriteInformation(self, record: InformationRecord) -> None: ...
    def WriteProgress(self, source_id: int, record: ProgressRecord) -> None: ...

class PSHostRawUserInterface:
    @property
    def BackgroundColor(self) -> ConsoleColor: ...
    @BackgroundColor.setter
    def BackgroundColor(self, value: ConsoleColor) -> None: ...
    @property
    def ForegroundColor(self) -> ConsoleColor: ...
    @ForegroundColor.setter
    def ForegroundColor(self, value: ConsoleColor) -> None: ...
    @property
    def BufferSize(self) -> Size: ...
    @BufferSize.setter
    def BufferSize(self, value: Size) -> None: ...
    @property
    def WindowSize(self) -> Size: ...
    @WindowSize.setter
    def WindowSize(self, value: Size) -> None: ...
    @property
    def WindowPosition(self) -> Coordinates: ...
    @WindowPosition.setter
    def WindowPosition(self, value: Coordinates) -> None: ...
    @property
    def CursorPosition(self) -> Coordinates: ...
    @CursorPosition.setter
    def CursorPosition(self, value: Coordinates) -> None: ...
    @property
    def CursorSize(self) -> int: ...
    @CursorSize.setter
    def CursorSize(self, value: int) -> None: ...
    @property
    def MaxWindowSize(self) -> Size: ...
    @property
    def MaxPhysicalWindowSize(self) -> Size: ...
    @property
    def KeyAvailable(self) -> bool: ...
