from __future__ import annotations

import os
import pathlib
import shutil
import types
from typing import Any, Self, overload

import pwinput
import pythonnet
import rich.console
import rich.markup
import rich.progress
import rich.style
import rich.text

# # For .NET Core:
# # Install .NET Runtime: (`winget install Microsoft.DotNet.Runtime.9`)
# pythonnet.load("coreclr")
# program_files = pathlib.Path(os.environ["ProgramFiles"])
# automation_root = program_files / "PowerShell" / "7"

# For .NET Framework:
pythonnet.load("netfx")
win_dir = pathlib.Path(os.environ["WinDir"])
automation_root = win_dir / "Microsoft.NET" / "assembly" / "GAC_MSIL" / "System.Management.Automation"

automation_dll = next(automation_root.rglob("System.Management.Automation.dll"), None)
if automation_dll is None:
    raise FileNotFoundError(f"System.Management.Automation.dll not found in {automation_root}")

import clr

clr.AddReference(str(automation_dll))

import System
import System.Management.Automation.Host
import System.Management.Automation.Runspaces
from System import ConsoleColor
from System.Collections.Generic import (
    Dictionary,
)
from System.Collections.ObjectModel import (
    Collection,
)
from System.Globalization import CultureInfo
from System.Management.Automation import (
    ErrorRecord,
    ProgressRecord,
    ProgressRecordType,
    PSCredential,
    PSCredentialTypes,
    PSCredentialUIOptions,
    PSObject,
    RuntimeException,
)
from System.Management.Automation.Host import (
    BufferCell,
    BufferCellType,
    ChoiceDescription,
    ControlKeyStates,
    Coordinates,
    FieldDescription,
    KeyInfo,
    PSHostUserInterface,
    ReadKeyOptions,
    Rectangle,
    Size,
)
from System.Security import SecureString

# Mapping between .NET ConsoleColor and rich color names, matching the standard console palette
_RICH_COLORS: dict[ConsoleColor, str] = {
    ConsoleColor.Black: "black",
    ConsoleColor.DarkBlue: "blue",
    ConsoleColor.DarkGreen: "green",
    ConsoleColor.DarkCyan: "cyan",
    ConsoleColor.DarkRed: "red",
    ConsoleColor.DarkMagenta: "magenta",
    ConsoleColor.DarkYellow: "yellow",
    ConsoleColor.Gray: "white",
    ConsoleColor.DarkGray: "bright_black",
    ConsoleColor.Blue: "bright_blue",
    ConsoleColor.Green: "bright_green",
    ConsoleColor.Cyan: "bright_cyan",
    ConsoleColor.Red: "bright_red",
    ConsoleColor.Magenta: "bright_magenta",
    ConsoleColor.Yellow: "bright_yellow",
    ConsoleColor.White: "bright_white",
}


class CustomPSHost(System.Management.Automation.Host.PSHost):
    """Custom PowerShell host implementation."""

    __namespace__ = "System.Management.Automation.Host"

    def __init__(self, ui: CustomPSHostUI) -> None:
        self._ui = ui
        self._name = "PythonPSHost"
        self._version = System.Version(1, 0)
        self._instance_id = System.Guid.NewGuid()
        self._debugger_enabled = False

    def get_CurrentCulture(self) -> CultureInfo:
        return CultureInfo.CurrentCulture

    def get_CurrentUICulture(self) -> CultureInfo:
        return CultureInfo.CurrentUICulture

    def get_DebuggerEnabled(self) -> bool:
        return self._debugger_enabled

    def get_InstanceId(self) -> System.Guid:
        return self._instance_id

    def get_Name(self) -> str:
        return self._name

    def get_PrivateData(self) -> None:
        return None

    def get_UI(self) -> PSHostUserInterface:
        return self._ui

    def get_Version(self) -> System.Version:
        return self._version

    def EnterNestedPrompt(self) -> None:
        """Requests a nested interactive prompt session"""

    def ExitNestedPrompt(self) -> None:
        """Exits a nested interactive prompt session"""

    def NotifyBeginApplication(self) -> None:
        """Called before executing external process"""

    def NotifyEndApplication(self) -> None:
        """Called after external process completes"""

    def SetShouldExit(self, exit_code: int) -> None:
        """Informs host that PowerShell wants to exit"""


class CustomPSHostUI(System.Management.Automation.Host.PSHostUserInterface):
    """Custom implementation of PowerShell host user interface."""

    __namespace__ = "System.Management.Automation.Host"

    def __init__(self) -> None:
        super().__init__()
        self._raw_ui = CustomPSHostRawUserInterface()
        self._supports_virtual_terminal = False
        self._err_console = rich.console.Console(stderr=True)
        self._progress: rich.progress.Progress | None = None
        # Mapping between powershell record source id + activity id and rich progress task id
        self._progress_tasks: dict[tuple[int, int], rich.progress.TaskID] = {}

    def get_RawUI(self) -> CustomPSHostRawUserInterface:
        return self._raw_ui

    def get_SupportsVirtualTerminal(self) -> bool:
        return self._supports_virtual_terminal

    def Prompt(
        self,
        caption: str | None,
        message: str | None,
        descriptions: list[FieldDescription],
    ) -> Dictionary[str, PSObject]:
        self._write_header(caption, message)

        results = Dictionary[str, PSObject]()
        for desc in descriptions:
            prompt = f"{desc.Name}: "
            if desc.HelpMessage:
                prompt = f"{desc.Name} ({desc.HelpMessage}): "
            if desc.ParameterTypeName == "SecureString":
                secure_str = self._read_secure_string(prompt)
                results.Add(desc.Name, PSObject(secure_str))
            else:
                user_input = input(prompt)
                results.Add(desc.Name, PSObject(user_input))
        return results

    def PromptForChoice(
        self,
        caption: str | None,
        message: str | None,
        choices: list[ChoiceDescription],
        default_choice: int,
    ) -> int:
        self._write_header(caption, message)

        # Labels mark their hotkey with an ampersand, e.g. "&Yes"
        hotkeys: dict[str, int] = {}
        labels: list[str] = []
        for idx, choice in enumerate(choices):
            label: str = choice.Label
            amp_idx = label.find("&")
            if 0 <= amp_idx < len(label) - 1:
                hotkeys[label[amp_idx + 1].upper()] = idx
                label = label[:amp_idx] + label[amp_idx + 1 :]
            labels.append(label)
            line = f"[{idx}] {label}"
            if choice.HelpMessage:
                line += f" - {choice.HelpMessage}"
            self._write(line, end="\n")

        # A default choice of -1 means there is no default
        has_default = 0 <= default_choice < len(choices)
        prompt = f"Choice [{labels[default_choice]}]: " if has_default else "Choice: "
        while True:
            user_input = input(prompt).strip()
            if not user_input and has_default:
                return default_choice
            if user_input.upper() in hotkeys:
                return hotkeys[user_input.upper()]
            if user_input.isdigit() and int(user_input) < len(choices):
                return int(user_input)
            self._write("Invalid choice. Please try again.", end="\n")

    @overload
    def PromptForCredential(self, caption: str, message: str, user_name: str, target_name: str) -> PSCredential: ...

    @overload
    def PromptForCredential(
        self,
        caption: str,
        message: str,
        user_name: str,
        target_name: str,
        allowed_credential_types: PSCredentialTypes,
        options: PSCredentialUIOptions,
    ) -> PSCredential: ...

    def PromptForCredential(
        self,
        caption: str,
        message: str,
        user_name: str,
        target_name: str,
        allowed_credential_types: PSCredentialTypes | None = None,
        options: PSCredentialUIOptions | None = None,
    ) -> PSCredential:
        self._write_header(caption, message)

        if user_name:
            self._write(f"User: {user_name}", end="\n")
        else:
            user_name = input("User: ")

        password = self._read_secure_string("Password: ")
        return PSCredential(user_name, password)

    def ReadLine(self) -> str:
        return input()

    def ReadLineAsSecureString(self) -> SecureString:
        return self._read_secure_string("")

    @overload
    def Write(self, value: str) -> None: ...

    @overload
    def Write(self, fg_color: ConsoleColor, bg_color: ConsoleColor, value: str) -> None: ...

    def Write(self, *args: Any) -> None:  # type: ignore[misc]
        nargs = len(args)
        if nargs == 1:
            self._write(args[0])
        elif nargs == 3:
            self._write(args[2], style=self._get_rich_style(args[0], args[1]))
        else:
            raise TypeError(f"Write takes 1 or 3 arguments, got {nargs}")

    def WriteDebugLine(self, message: str) -> None:
        self._write(f"DEBUG: {message}", style="yellow", end="\n")

    def WriteErrorLine(self, message: str) -> None:
        self._write(f"ERROR: {message}", style="bright_red", end="\n", console=self._err_console)

    @overload
    def WriteLine(self) -> None: ...

    @overload
    def WriteLine(self, value: str) -> None: ...

    @overload
    def WriteLine(self, fg_color: ConsoleColor, bg_color: ConsoleColor, value: str) -> None: ...

    def WriteLine(self, *args: Any) -> None:  # type: ignore[misc]
        nargs = len(args)
        if nargs == 0:
            self._write("", end="\n")
        elif nargs == 1:
            self._write(args[0], end="\n")
        elif nargs == 3:
            self._write(args[2], style=self._get_rich_style(args[0], args[1]), end="\n")
        else:
            raise TypeError(f"WriteLine takes 0, 1, or 3 arguments, got {nargs}")

    def WriteProgress(self, source_id: int, record: ProgressRecord) -> None:
        key: tuple[int, int] = (source_id, record.ActivityId)
        task_id = self._progress_tasks.get(key)

        if record.RecordType == ProgressRecordType.Completed:
            if task_id is not None and self._progress is not None:
                del self._progress_tasks[key]
                self._progress.remove_task(task_id)
                if not self._progress_tasks:
                    self.stop_progress()
            return

        if self._progress is None:
            self._progress = rich.progress.Progress(transient=True, expand=True)
            self._progress.start()

        # Progress descriptions are parsed as rich markup
        description = rich.markup.escape(record.Activity)
        if record.StatusDescription:
            description += f" - {rich.markup.escape(record.StatusDescription)}"

        # Negative percentage means it is unknown
        percent: int = record.PercentComplete
        if task_id is None:
            self._progress_tasks[key] = self._progress.add_task(
                description=description,
                total=100 if percent >= 0 else None,
                completed=max(percent, 0),
            )
        elif percent >= 0:
            self._progress.update(task_id, description=description, total=100, completed=percent)
        else:
            self._progress.update(task_id, description=description)

    def WriteVerboseLine(self, message: str) -> None:
        self._write(f"VERBOSE: {message}", style="yellow", end="\n")

    def WriteWarningLine(self, message: str) -> None:
        self._write(f"WARNING: {message}", style="yellow", end="\n")

    def stop_progress(self) -> None:
        """Hide all progress bars, e.g. when a pipeline ended without completing them."""
        if self._progress is not None:
            self._progress.stop()
            self._progress = None
        self._progress_tasks.clear()

    def _write(
        self,
        text: str,
        style: str | rich.style.Style | None = None,
        end: str = "",
        console: rich.console.Console | None = None,
    ) -> None:
        """Print text as is, without rich markup, highlighting or wrapping."""
        console = console or rich.get_console()
        console.print(rich.text.Text(text, style=style or ""), end=end, soft_wrap=True)
        console.file.flush()

    def _write_header(self, caption: str | None, message: str | None) -> None:
        """Print caption and message of a prompt."""
        if caption:
            self._write(caption, end="\n")
        if message:
            self._write(message, end="\n")

    def _read_secure_string(self, prompt: str) -> SecureString:
        """Read secure string with asterisk masking."""
        secure_str = SecureString()
        for char in pwinput.pwinput(prompt):
            secure_str.AppendChar(char)
        secure_str.MakeReadOnly()

        return secure_str

    def _get_rich_style(self, fg_color: ConsoleColor, bg_color: ConsoleColor) -> rich.style.Style:
        """Map .NET ConsoleColor to rich style, keeping terminal defaults for host default colors"""
        fg_name = None if fg_color == self._raw_ui.get_ForegroundColor() else _RICH_COLORS.get(fg_color)
        bg_name = None if bg_color == self._raw_ui.get_BackgroundColor() else _RICH_COLORS.get(bg_color)
        return rich.style.Style(color=fg_name, bgcolor=bg_name)


class CustomPSHostRawUserInterface(System.Management.Automation.Host.PSHostRawUserInterface):
    """Minimal implementation of PowerShell's raw user interface for console operations."""

    __namespace__ = "System.Management.Automation.Host"

    def __init__(self) -> None:
        columns, lines = shutil.get_terminal_size(fallback=(120, 30))

        self._background_color = ConsoleColor.Black
        self._foreground_color = ConsoleColor.White
        self._buffer_size = Size(columns, lines)
        self._window_size = Size(columns, lines)
        self._window_position = Coordinates(0, 0)
        self._cursor_position = Coordinates(0, 0)
        self._cursor_size = 1  # Percentage (1-100)
        self._max_window_size = Size(columns, lines)
        self._max_physical_window_size = Size(columns, lines)
        self._window_title = ""

        self._buffer: list[list[BufferCell]] = []
        self._resize_buffer()

    # Pythonnet overrides .NET properties through get_/set_ methods, not Python properties

    def get_BackgroundColor(self) -> ConsoleColor:
        return self._background_color

    def set_BackgroundColor(self, value: ConsoleColor) -> None:
        self._background_color = value

    def get_ForegroundColor(self) -> ConsoleColor:
        return self._foreground_color

    def set_ForegroundColor(self, value: ConsoleColor) -> None:
        self._foreground_color = value

    def get_BufferSize(self) -> Size:
        return self._buffer_size

    def set_BufferSize(self, value: Size) -> None:
        self._buffer_size = value
        self._resize_buffer()

    def get_WindowSize(self) -> Size:
        return self._window_size

    def set_WindowSize(self, value: Size) -> None:
        self._window_size = value

    def get_WindowPosition(self) -> Coordinates:
        return self._window_position

    def set_WindowPosition(self, value: Coordinates) -> None:
        self._window_position = value

    def get_CursorPosition(self) -> Coordinates:
        return self._cursor_position

    def set_CursorPosition(self, value: Coordinates) -> None:
        self._cursor_position = value

    def get_CursorSize(self) -> int:
        return self._cursor_size

    def set_CursorSize(self, value: int) -> None:
        if 1 <= value <= 100:
            self._cursor_size = value

    def get_MaxWindowSize(self) -> Size:
        return self._max_window_size

    def get_MaxPhysicalWindowSize(self) -> Size:
        return self._max_physical_window_size

    def get_WindowTitle(self) -> str:
        return self._window_title

    def set_WindowTitle(self, value: str) -> None:
        self._window_title = value

    def get_KeyAvailable(self) -> bool:
        return System.Console.KeyAvailable

    def FlushInputBuffer(self) -> None:
        """Clear any pending key presses in the input buffer."""
        while System.Console.KeyAvailable:
            System.Console.ReadKey(True)

    def GetBufferContents(self, rectangle: Rectangle) -> Any:
        """Returns a 2D array (BufferCell[,]) of cells representing the console buffer area."""
        width = max(rectangle.Right - rectangle.Left + 1, 0)
        height = max(rectangle.Bottom - rectangle.Top + 1, 0)

        cell_grid = System.Array.CreateInstance(BufferCell, height, width)
        for row_idx in range(height):
            for col_idx in range(width):
                x = rectangle.Left + col_idx
                y = rectangle.Top + row_idx
                # Return default cell if out of bounds
                cell_grid[row_idx, col_idx] = (
                    self._buffer[y][x] if self._is_valid_position(x, y) else self._empty_cell()
                )

        return cell_grid

    @overload
    def ReadKey(self) -> KeyInfo: ...

    @overload
    def ReadKey(self, options: ReadKeyOptions) -> KeyInfo: ...

    def ReadKey(self, *args: Any) -> KeyInfo:  # type: ignore[misc]
        """
        Reads the next keystroke, waiting until a key is pressed.

        Args:
            *args: Either empty (default options) or a single ReadKeyOptions value.

        Returns:
            KeyInfo: Information about the pressed key.

        Raises:
            TypeError: If incorrect number of arguments provided.
        """
        nargs = len(args)

        if nargs == 0:
            key_options = ReadKeyOptions.IncludeKeyDown
        elif nargs == 1:
            key_options = args[0]
        else:
            raise TypeError("ReadKey takes 0 or 1 arguments")

        # Determine intercept (suppress echo) based on NoEcho option
        intercept = key_options.HasFlag(ReadKeyOptions.NoEcho)
        console_key_info = System.Console.ReadKey(intercept)

        # Map modifiers to ControlKeyStates
        control_key_state = ControlKeyStates(0)
        modifiers = console_key_info.Modifiers

        if modifiers.HasFlag(System.ConsoleModifiers.Shift):
            control_key_state |= ControlKeyStates.ShiftPressed
        if modifiers.HasFlag(System.ConsoleModifiers.Alt):
            control_key_state |= ControlKeyStates.LeftAltPressed
        if modifiers.HasFlag(System.ConsoleModifiers.Control):
            control_key_state |= ControlKeyStates.LeftCtrlPressed

        # Add lock key states
        if System.Console.CapsLock:
            control_key_state |= ControlKeyStates.CapsLockOn
        if System.Console.NumberLock:
            control_key_state |= ControlKeyStates.NumLockOn

        return KeyInfo(
            int(console_key_info.Key),  # Virtual key code
            console_key_info.KeyChar,  # Character representation
            control_key_state,  # Modifier flags
            True,  # KeyDown=True (always)
        )

    def ScrollBufferContents(
        self,
        source: Rectangle,
        destination: Coordinates,
        clip: Rectangle,
        fill: BufferCell,
    ) -> None:
        """
        Scrolls a region of the buffer, moving content from a source rectangle to a destination location.
        The vacated area is filled with the specified fill cell.

        Args:
            source: Source rectangle to scroll
            destination: Top-left coordinates of destination area
            clip: Clipping rectangle (only this area is affected)
            fill: Cell to fill in vacated areas
        """

        def in_clip(x: int, y: int) -> bool:
            return clip.Left <= x <= clip.Right and clip.Top <= y <= clip.Bottom and self._is_valid_position(x, y)

        # Calculate scroll vector
        dx = destination.X - source.Left
        dy = destination.Y - source.Top

        # Keep the original state to copy from, as source and destination may overlap
        old_buffer = [row[:] for row in self._buffer]

        # Fill the source area first, so the moved content written over it is preserved
        for y in range(source.Top, source.Bottom + 1):
            for x in range(source.Left, source.Right + 1):
                if in_clip(x, y):
                    self._buffer[y][x] = fill

        for y in range(source.Top, source.Bottom + 1):
            for x in range(source.Left, source.Right + 1):
                if self._is_valid_position(x, y) and in_clip(x + dx, y + dy):
                    self._buffer[y + dy][x + dx] = old_buffer[y][x]

    @overload
    def SetBufferContents(self, rectangle: Rectangle, cell: BufferCell) -> None: ...

    @overload
    def SetBufferContents(self, origin: Coordinates, contents: Any) -> None: ...

    def SetBufferContents(  # type: ignore[misc]
        self,
        arg1: Any,
        arg2: Any,
    ) -> None:
        """
        Sets buffer contents.
        Handles both overloads:
          1. Fill rectangle with a single cell
          2. Write content grid (BufferCell[,]) starting at origin
        """
        if isinstance(arg1, Rectangle) and isinstance(arg2, BufferCell):
            self._fill_rectangle(arg1, arg2)
        elif isinstance(arg1, Coordinates) and isinstance(arg2, System.Array) and arg2.Rank == 2:
            self._write_content(arg1, arg2)
        else:
            raise TypeError("Invalid argument types for SetBufferContents")

    def _empty_cell(self) -> BufferCell:
        return BufferCell(" ", self._foreground_color, self._background_color, BufferCellType.Complete)

    def _resize_buffer(self) -> None:
        """Resize the internal buffer to the buffer size, keeping existing cells"""
        width = self._buffer_size.Width
        height = self._buffer_size.Height

        new_buffer = []
        for y in range(height):
            row = []
            for x in range(width):
                row.append(self._buffer[y][x] if self._is_valid_position(x, y) else self._empty_cell())
            new_buffer.append(row)
        self._buffer = new_buffer

    def _is_valid_position(self, x: int, y: int) -> bool:
        """Check if coordinates are within buffer bounds"""
        return (0 <= y < len(self._buffer)) and (0 <= x < len(self._buffer[0]))

    def _fill_rectangle(self, rectangle: Rectangle, fill: BufferCell) -> None:
        """Fill a rectangular region with the specified cell"""
        # Rectangle with all coordinates set to -1 means the whole buffer, used by Clear-Host
        if rectangle.Left == rectangle.Top == rectangle.Right == rectangle.Bottom == -1:
            rectangle = Rectangle(0, 0, self._buffer_size.Width - 1, self._buffer_size.Height - 1)
            rich.get_console().clear()

        for y in range(rectangle.Top, rectangle.Bottom + 1):
            for x in range(rectangle.Left, rectangle.Right + 1):
                if self._is_valid_position(x, y):
                    self._buffer[y][x] = fill

    def _write_content(self, origin: Coordinates, contents: Any) -> None:
        """Write a grid of cells (BufferCell[,]) starting at the specified origin"""
        for y in range(contents.GetLength(0)):
            for x in range(contents.GetLength(1)):
                pos_x = origin.X + x
                pos_y = origin.Y + y
                if self._is_valid_position(pos_x, pos_y):
                    self._buffer[pos_y][pos_x] = contents[y, x]


class PowerShellError(Exception):
    """Exception raised when a PowerShell command encounters execution errors."""

    def __init__(self, errors: list[ErrorRecord]) -> None:
        """
        Initialize PowerShellError with collected error information.

        Args:
            errors: List of PowerShell error records.
        """
        self.errors = errors
        message = "PowerShell command failed with errors:\n" + "\n".join(str(e) for e in errors)
        super().__init__(message)


class PowerShell:
    """Wrapper for executing PowerShell commands, getting properties and formatting results."""

    def __init__(self) -> None:
        self._ui = CustomPSHostUI()
        host = CustomPSHost(self._ui)

        self._runspace = System.Management.Automation.Runspaces.RunspaceFactory.CreateRunspace(host)
        self._runspace.Open()

        self.pwsh = System.Management.Automation.PowerShell.Create()
        self.pwsh.Runspace = self._runspace

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        type_: type[BaseException] | None,
        value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release the PowerShell instance and its runspace."""
        self._ui.stop_progress()
        self.pwsh.Dispose()
        self._runspace.Dispose()

    def execute_script(self, script: str) -> Collection[PSObject]:
        """
        Execute a PowerShell script and return results.

        Args:
            script: PowerShell script to execute

        Returns:
            Collection of result objects from the script

        Raises:
            PowerShellError: If the script produces any errors
        """
        self.pwsh.Commands.Clear()
        self.pwsh.Commands.AddScript(script)
        return self._invoke()

    def format_output(self, target: Collection[PSObject]) -> str:
        """
        Format PowerShell output as they would appear in a PowerShell console.

        Args:
            target: Collection of objects returned from execute_script()

        Returns:
            Formatted output string
        """
        if not target:
            return ""

        self.pwsh.Commands.Clear()
        self.pwsh.Commands.AddCommand("Out-String")
        formatted = self._invoke(target)

        return "".join(str(obj) for obj in formatted)

    def get_property(self, target: Collection[PSObject], property: str) -> Any:
        """
        Extract a specific property value from the first PowerShell output object.

        Args:
            target: Collection of PowerShell output objects from execute_script()
            property: Name of the property which value should be retrieved

        Returns:
            Property value

        Raises:
            ValueError: If target is empty
            KeyError: If the object has no such property
        """
        # Script producing $null returns a collection with single null item
        if not target or target[0] is None:
            raise ValueError(f"Cannot get property '{property}' of empty PowerShell output")

        ps_property = target[0].Properties[property]
        if ps_property is None:
            raise KeyError(f"PowerShell output object has no property '{property}'")

        return ps_property.Value

    def get_str_property(self, target: Collection[PSObject], property: str) -> str:
        """
        Extract a specific property value from the first PowerShell output object in human-readable format.

        Args:
            target: Collection of PowerShell output objects from execute_script()
            property: Name of the property which value should be retrieved

        Returns:
            Property value, or empty string if the value is null

        Raises:
            ValueError: If target is empty
            KeyError: If the object has no such property
        """
        if self.get_property(target, property) is None:
            return ""

        first = Collection[PSObject]()
        first.Add(target[0])

        self.pwsh.Commands.Clear()
        self.pwsh.Commands.AddCommand("Select-Object").AddParameter("ExpandProperty", property)
        results = self._invoke(first)

        return str(results[0]) if results else ""

    def _invoke(self, input: Collection[PSObject] | None = None) -> Collection[PSObject]:
        """
        Invoke the current commands, raising PowerShellError on both terminating and non-terminating errors.
        """
        self.pwsh.Streams.ClearStreams()
        try:
            result = self.pwsh.Invoke() if input is None else self.pwsh.Invoke(input)
        except RuntimeException as e:
            raise PowerShellError([*self.pwsh.Streams.Error, e.ErrorRecord]) from e
        finally:
            self._ui.stop_progress()

        if self.pwsh.HadErrors:
            raise PowerShellError(list(self.pwsh.Streams.Error))

        return result
