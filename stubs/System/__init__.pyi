from enum import IntEnum
from typing import ClassVar, TypeVar

from System.Management.Automation.Host import ConsoleColor as ConsoleColor

_T = TypeVar("_T")

class Version:
    Major: int
    Minor: int
    Build: int
    Revision: int
    def __init__(self, major: int, minor: int, build: int | None = None, revision: int | None = None) -> None: ...
    def __str__(self) -> str: ...

class Guid:
    @staticmethod
    def NewGuid() -> Guid: ...
    def __str__(self) -> str: ...
    def __eq__(self, other: object) -> bool: ...

class ConsoleModifiers(IntEnum):
    Shift = 1
    Alt = 2
    Control = 4

class ConsoleKeyInfo:
    Key: int
    KeyChar: str
    Modifiers: ConsoleModifiers

class Console:
    KeyAvailable: ClassVar[bool]
    CapsLock: ClassVar[bool]
    NumberLock: ClassVar[bool]
    @staticmethod
    def ReadKey(intercept: bool) -> ConsoleKeyInfo: ...
    @staticmethod
    def Clear() -> None: ...
