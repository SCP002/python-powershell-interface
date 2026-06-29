from __future__ import annotations

import os
import pathlib
import sys
import types
from typing import Any, overload

import pwinput
import pythonnet
import rich.progress
import rich.style

# For .NET Core, runtime should be "coreclr"
pythonnet.load("default")

win_dir = pathlib.Path(os.environ["WinDir"])
# For .NET Core, automation_root should be "C:\Program Files\PowerShell\7"
automation_root = win_dir / "Microsoft.NET" / "assembly" / "GAC_MSIL" / "System.Management.Automation"
automation_dll = str(next(automation_root.rglob("System.Management.Automation.dll")))

import clr

clr.AddReference(automation_dll)  # pyright: ignore[reportAttributeAccessIssue]

import System  # pyright: ignore[reportMissingImports]
import System.Management.Automation.Host  # pyright: ignore[reportMissingImports]
import System.Management.Automation.Runspaces  # pyright: ignore[reportMissingImports]
from System import ConsoleColor  # pyright: ignore[reportMissingImports]
from System.Collections.Generic import (  # pyright: ignore[reportMissingImports]
    Dictionary,
)
from System.Collections.ObjectModel import (  # pyright: ignore[reportMissingImports]
    Collection,
)
from System.Globalization import CultureInfo  # pyright: ignore[reportMissingImports]
from System.Management.Automation import (  # pyright: ignore[reportMissingImports]
    InformationRecord,
    ProgressRecord,
    ProgressRecordType,
    PSCredential,
    PSCredentialTypes,
    PSCredentialUIOptions,
    PSObject,
)
from System.Management.Automation.Host import (  # pyright: ignore[reportMissingImports]
    BufferCell,
    BufferCellType,
    ChoiceDescription,
    ControlKeyStates,
    Coordinates,
    FieldDescription,
    KeyInfo,
    PromptingException,
    ReadKeyOptions,
    Rectangle,
    Size,
)
from System.Security import SecureString  # pyright: ignore[reportMissingImports]


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

    def get_UI(self) -> CustomPSHostUI:
        return self._ui

    def get_Version(self) -> System.Version:
        return self._version

    def EnterNestedPrompt(self) -> None:
        """Requests a nested interactive prompt session"""
        pass

    def ExitNestedPrompt(self) -> None:
        """Exits a nested interactive prompt session"""
        pass

    def NotifyBeginApplication(self) -> None:
        """Called before executing external process"""
        pass

    def NotifyEndApplication(self) -> None:
        """Called after external process completes"""
        pass

    def SetShouldExit(self, exit_code: int) -> None:
        """Informs host that PowerShell wants to exit"""
        pass


class CustomPSHostUI(System.Management.Automation.Host.PSHostUserInterface):
    """Custom implementation of PowerShell host user interface."""

    __namespace__ = "System.Management.Automation.Host"

    def __init__(self) -> None:
        super(CustomPSHostUI, self).__init__()
        self._raw_ui = CustomPSHostRawUserInterface()
        self._supports_virtual_terminal = False
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
        if caption:
            sys.stdout.write(f"{caption}\n")
        if message:
            sys.stdout.write(f"{message}\n")

        results = Dictionary[str, PSObject]()
        for desc in descriptions:
            prompt = f"{desc.Name}: "
            if desc.HelpMessage:
                prompt += f"({desc.HelpMessage}) "
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
        default_choice: int | None,
    ) -> int:
        # Display caption and message
        if caption:
            sys.stdout.write(f"{caption}\n")
        if message:
            sys.stdout.write(f"{message}\n")

        for idx, choice in enumerate(choices):
            sys.stdout.write(f"[{idx}] {choice.get_Label()}\n")

        # Prompt for input with default
        prompt = f"Choice [{default_choice}]: "
        while True:
            user_input = input(prompt).strip()
            if not user_input and default_choice is not None:
                return default_choice
            try:
                choice_idx = int(user_input)
                if 0 <= choice_idx < len(choices):
                    return choice_idx
            except ValueError:
                pass
            sys.stdout.write("Invalid choice. Please try again.\n")

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

    def PromptForCredential(  # pyright: ignore[reportInconsistentOverload]
        self,
        caption: str,
        message: str,
        user_name: str,
        target_name: str,
        allowed_credential_types: PSCredentialTypes,
        options: PSCredentialUIOptions,
    ) -> PSCredential:
        if caption:
            sys.stdout.write(f"{caption}\n")
        if message:
            sys.stdout.write(f"{message}\n")

        if user_name:
            sys.stdout.write(f"User: {user_name}\n")
        else:
            user_name = input("User: ")

        password = self._read_secure_string("")
        return PSCredential(user_name, password)

    def ReadLine(self) -> str:
        return input()

    def ReadLineAsSecureString(self) -> SecureString:
        return self._read_secure_string("")

    @overload
    def Write(self, value: str) -> None: ...

    @overload
    def Write(self, fg_color: ConsoleColor, bg_color: ConsoleColor, value: str) -> None: ...

    def Write(self, *args) -> None:  # pyright: ignore[reportInconsistentOverload]
        nargs = len(args)
        if nargs == 1:
            value: str = args[0]
            rich.get_console().print(value, end="")
        elif nargs == 3:
            fg_color: ConsoleColor = args[0]
            bg_color: ConsoleColor = args[1]
            value: str = args[2]
            style = self._get_rich_style(fg_color, bg_color)
            rich.get_console().print(value, style=style, end="")
        else:
            raise TypeError(f"Write takes 1 or 3 arguments, got {nargs}")
        rich.get_console().file.flush()

    def WriteDebugLine(self, message: str) -> None:
        sys.stdout.write(f"DEBUG: {message}\n")

    def WriteErrorLine(self, message: str) -> None:
        sys.stderr.write(f"ERROR: {message}\n")

    def WriteInformation(self, informaton_record: InformationRecord) -> None:
        super().WriteInformation(informaton_record)

    @overload
    def WriteLine(self) -> None: ...

    @overload
    def WriteLine(self, value: str) -> None: ...

    @overload
    def WriteLine(self, fg_color: ConsoleColor, bg_color: ConsoleColor, value: str) -> None: ...

    def WriteLine(self, *args) -> None:  # pyright: ignore[reportInconsistentOverload]
        nargs = len(args)
        if nargs == 0:
            sys.stdout.write("\n")
        elif nargs == 1:
            value: str = args[0]
            rich.get_console().print(value)
        elif nargs == 3:
            fg_color: ConsoleColor = args[0]
            bg_color: ConsoleColor = args[1]
            value: str = args[2]
            style = self._get_rich_style(fg_color, bg_color)
            rich.get_console().print(value, style=style)
        else:
            raise TypeError(f"WriteLine takes 0, 1, or 3 arguments, got {nargs}")
        rich.get_console().file.flush()

    def WriteProgress(self, source_id: int, record: ProgressRecord) -> None:
        key: tuple[int, int] = (source_id, record.ActivityId)

        if self._progress is None:
            self._progress = rich.progress.Progress(transient=True, expand=True)
            self._progress.start()

        if key in self._progress_tasks:
            task_id = self._progress_tasks[key]
        else:
            task_id = self._progress.add_task(description=f"{record.Activity}", total=100, start=False)
            self._progress_tasks[key] = task_id
            self._progress.start_task(task_id)

        if record.PercentComplete == 100 or record.RecordType == ProgressRecordType.Completed:
            del self._progress_tasks[key]
            if len(self._progress_tasks) == 0:
                self._progress.stop()
                self._progress.update(task_id, visible=False)
            self._progress.remove_task(task_id)
            return

        update_args: dict[str, Any] = {}

        if record.PercentComplete >= 0:
            update_args["completed"] = record.PercentComplete
        if record.StatusDescription:
            update_args["description"] = f"{record.Activity} - {record.StatusDescription}"

        self._progress.update(task_id, **update_args)

    def WriteVerboseLine(self, message: str) -> None:
        sys.stdout.write(f"VERBOSE: {message}\n")

    def WriteWarningLine(self, message: str) -> None:
        sys.stdout.write(f"WARNING: {message}\n")

    def _read_secure_string(self, prompt: str) -> SecureString:
        """Read secure string with asterisk masking."""
        secure_str = SecureString()
        for char in pwinput.pwinput(prompt):
            secure_str.AppendChar(char)

        return secure_str

    def _get_rich_style(self, fg_color: ConsoleColor, bg_color: ConsoleColor) -> rich.style.Style:
        """Map .NET ConsoleColor to rich style"""
        color_map = {
            ConsoleColor.Black: "black",
            ConsoleColor.DarkBlue: "dark_blue",
            ConsoleColor.DarkGreen: "dark_green",
            ConsoleColor.DarkCyan: "dark_cyan",
            ConsoleColor.DarkRed: "dark_red",
            ConsoleColor.DarkMagenta: "dark_magenta",
            ConsoleColor.DarkYellow: "dark_yellow",
            ConsoleColor.Gray: "grey50",
            ConsoleColor.DarkGray: "grey30",
            ConsoleColor.Blue: "blue",
            ConsoleColor.Green: "green",
            ConsoleColor.Cyan: "cyan",
            ConsoleColor.Red: "red",
            ConsoleColor.Magenta: "magenta",
            ConsoleColor.Yellow: "yellow",
            ConsoleColor.White: "white",
        }
        fg_name = color_map.get(fg_color, "white")
        bg_name = color_map.get(bg_color, "black")
        return rich.style.Style(color=fg_name, bgcolor=bg_name)


class CustomPSHostRawUserInterface(System.Management.Automation.Host.PSHostRawUserInterface):
    """Minimal implementation of PowerShell's raw user interface for console operations."""

    __namespace__ = "System.Management.Automation.Host"

    def __init__(self) -> None:
        self._background_color = ConsoleColor.Black
        self._foreground_color = ConsoleColor.White
        self._buffer_size = Size(120, 30)
        self._window_size = Size(120, 30)
        self._window_position = Coordinates(0, 0)
        self._cursor_position = Coordinates(0, 0)
        self._cursor_size = 1  # Percentage (1-100)
        self._max_window_size = Size(120, 30)
        self._max_physical_window_size = Size(120, 30)

        # Initialize internal buffer representation
        self._buffer = []
        self._initialize_buffer()

    def get_BackgroundColor(self) -> ConsoleColor:
        return self._background_color

    def set_BackgroundColor(self, value: ConsoleColor) -> None:
        self._background_color = value

    BackgroundColor = property(get_BackgroundColor, set_BackgroundColor)

    def get_ForegroundColor(self) -> ConsoleColor:
        return self._foreground_color

    def set_ForegroundColor(self, value: ConsoleColor) -> None:
        self._foreground_color = value

    ForegroundColor = property(get_ForegroundColor, set_ForegroundColor)

    def get_BufferSize(self) -> Size:
        return self._buffer_size

    def set_BufferSize(self, value: Size) -> None:
        self._buffer_size = value

    BufferSize = property(get_BufferSize, set_BufferSize)

    def get_WindowSize(self) -> Size:
        return self._window_size

    def set_WindowSize(self, value: Size) -> None:
        self._window_size = value

    WindowSize = property(get_WindowSize, set_WindowSize)

    def get_WindowPosition(self) -> Coordinates:
        return self._window_position

    def set_WindowPosition(self, value: Coordinates) -> None:
        self._window_position = value

    WindowPosition = property(get_WindowPosition, set_WindowPosition)

    def get_CursorPosition(self) -> Coordinates:
        return self._cursor_position

    def set_CursorPosition(self, value: Coordinates) -> None:
        self._cursor_position = value

    CursorPosition = property(get_CursorPosition, set_CursorPosition)

    def get_CursorSize(self) -> int:
        return self._cursor_size

    def set_CursorSize(self, value: int) -> None:
        if 1 <= value <= 100:
            self._cursor_size = value

    CursorSize = property(get_CursorSize, set_CursorSize)

    def get_MaxWindowSize(self) -> Size:
        return self._max_window_size

    MaxWindowSize = property(get_MaxWindowSize, None)

    def get_MaxPhysicalWindowSize(self) -> Size:
        return self._max_physical_window_size

    MaxPhysicalWindowSize = property(get_MaxPhysicalWindowSize, None)

    def get_KeyAvailable(self) -> bool:
        return System.Console.KeyAvailable

    KeyAvailable = property(get_KeyAvailable, None)

    def FlushInputBuffer(self) -> None:
        """Clear any pending key presses in the input buffer."""
        while System.Console.KeyAvailable:
            System.Console.ReadKey(True)

    def GetBufferContents(self, rectangle: Rectangle) -> list[list[BufferCell]]:
        """Returns a grid of BufferCell objects representing the console buffer area."""
        width = rectangle.Right - rectangle.Left + 1
        height = rectangle.Bottom - rectangle.Top + 1

        cell_grid = []
        for y in range(rectangle.Top, rectangle.Top + height):
            row = []
            for x in range(rectangle.Left, rectangle.Left + width):
                if self._is_valid_position(x, y):
                    row.append(self._buffer[y][x])
                else:
                    # Return default cell if out of bounds
                    row.append(BufferCell(" ", self.ForegroundColor, self.BackgroundColor, BufferCellType.Complete))
            cell_grid.append(row)

        return cell_grid

    @overload
    def ReadKey(self) -> KeyInfo: ...

    @overload
    def ReadKey(self, options: ReadKeyOptions) -> KeyInfo: ...

    def ReadKey(self, *args) -> KeyInfo:  # pyright: ignore[reportInconsistentOverload]
        """
        Reads the next keystroke, with optional ReadKeyOptions.
        Args:
            *args: Either empty (default options) or a single ReadKeyOptions value.
        Returns:
            KeyInfo: Information about the pressed key.
        Raises:
            TypeError: If incorrect number of arguments provided.
            PromptingException: If no key available and not waiting.
        """
        options = ReadKeyOptions()
        nargs = len(args)

        if nargs == 0:
            pass  # Use default options
        elif nargs == 1:
            options: ReadKeyOptions = args[0]
        else:
            raise TypeError("ReadKey takes 0 or 1 arguments")

        # Check if key is available when not waiting
        if (options & ReadKeyOptions.WaitOnKey) == 0 and not System.Console.KeyAvailable:
            raise PromptingException()

        # Determine intercept (suppress echo) based on NoEcho option
        intercept = (options & ReadKeyOptions.NoEcho) != 0
        console_key_info = System.Console.ReadKey(intercept)

        # Map modifiers to ControlKeyStates
        control_key_state = ControlKeyStates(0)
        modifiers = console_key_info.Modifiers

        if (modifiers & System.ConsoleModifiers.Shift) != 0:
            control_key_state |= ControlKeyStates.ShiftPressed
        if (modifiers & System.ConsoleModifiers.Alt) != 0:
            control_key_state |= ControlKeyStates.LeftAltPressed | ControlKeyStates.RightAltPressed
        if (modifiers & System.ConsoleModifiers.Control) != 0:
            control_key_state |= ControlKeyStates.LeftCtrlPressed | ControlKeyStates.RightCtrlPressed

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
        # Calculate scroll vector
        dx = destination.X - source.Left
        dy = destination.Y - source.Top

        # Create a copy of the current buffer state
        new_buffer = [row[:] for row in self._buffer]

        # Process each cell in the source rectangle
        for y in range(source.Top, source.Bottom + 1):
            for x in range(source.Left, source.Right + 1):
                # Only process if within clip region
                if clip.Left <= x <= clip.Right and clip.Top <= y <= clip.Bottom:

                    # Calculate new position
                    new_x = x + dx
                    new_y = y + dy

                    # Only move if both source and destination are in buffer bounds
                    if self._is_valid_position(x, y) and self._is_valid_position(new_x, new_y):
                        new_buffer[new_y][new_x] = self._buffer[y][x]

        # Fill vacated source area that is within clip region
        for y in range(source.Top, source.Bottom + 1):
            for x in range(source.Left, source.Right + 1):
                if clip.Left <= x <= clip.Right and clip.Top <= y <= clip.Bottom and self._is_valid_position(x, y):
                    new_buffer[y][x] = fill

        # Update buffer with new state
        self._buffer = new_buffer

    @overload
    def SetBufferContents(self, rectangle: Rectangle, cell: BufferCell) -> None: ...

    @overload
    def SetBufferContents(self, origin: Coordinates, contents: list[list[BufferCell]]) -> None: ...

    def SetBufferContents(  # pyright: ignore[reportInconsistentOverload]
        self, arg1: Rectangle | Coordinates, arg2: BufferCell | list[list[BufferCell]]
    ) -> None:
        """
        Sets buffer contents.
        Handles both overloads:
          1. Fill rectangle with a single cell
          2. Write content grid starting at origin
        """
        if isinstance(arg1, Rectangle) and isinstance(arg2, BufferCell):
            self._fill_rectangle(arg1, arg2)
        elif isinstance(arg1, Coordinates) and isinstance(arg2, list) and all(isinstance(row, list) for row in arg2):
            self._write_content(arg1, arg2)
        else:
            raise TypeError("Invalid argument types for SetBufferContents")

    def _initialize_buffer(self) -> None:
        """Initialize the internal buffer with empty cells"""
        width = self._buffer_size.Width
        height = self._buffer_size.Height

        self._buffer = []
        for y in range(height):
            row = []
            for x in range(width):
                row.append(BufferCell(" ", self.ForegroundColor, self.BackgroundColor, BufferCellType.Complete))
            self._buffer.append(row)

    def _is_valid_position(self, x: int, y: int) -> bool:
        """Check if coordinates are within buffer bounds"""
        return (0 <= y < len(self._buffer)) and (0 <= x < len(self._buffer[0]))

    def _fill_rectangle(self, rectangle: Rectangle, fill: BufferCell) -> None:
        """Fill a rectangular region with the specified cell"""
        for y in range(rectangle.Top, rectangle.Bottom + 1):
            for x in range(rectangle.Left, rectangle.Right + 1):
                if self._is_valid_position(x, y):
                    self._buffer[y][x] = fill

    def _write_content(self, origin: Coordinates, contents: list[list[BufferCell]]) -> None:
        """Write a grid of cells starting at the specified origin"""
        for y, row in enumerate(contents):
            for x, cell in enumerate(row):
                pos_x = origin.X + x
                pos_y = origin.Y + y
                if self._is_valid_position(pos_x, pos_y):
                    self._buffer[pos_y][pos_x] = cell


class PowerShellError(Exception):
    """Exception raised when a PowerShell command encounters execution errors."""

    def __init__(self, errors: list[Any]) -> None:
        """
        Initialize PowerShellError with collected error information.
        Args:
            errors: List of PowerShell error objects.
        """
        message = "PowerShell command failed with errors:\n" + "\n".join(str(e) for e in errors)
        super().__init__(message)


class PowerShell:
    """Wrapper for executing PowerShell commands, getting properties and formatting results."""

    def __init__(self) -> None:
        ui = CustomPSHostUI()
        host = CustomPSHost(ui)

        runspace = System.Management.Automation.Runspaces.RunspaceFactory.CreateRunspace(host)
        runspace.Open()

        self.pwsh = System.Management.Automation.PowerShell.Create()
        self.pwsh.Runspace = runspace

    def __enter__(self):
        return self

    def __exit__(
        self,
        type_: type[BaseException] | None,
        value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> bool | None:
        self.pwsh.Dispose()

    def execute_command(self, cmd: str) -> Collection[PSObject]:
        """
        Execute a PowerShell command and return results.
        Args:
            cmd: PowerShell command/script to execute
        Returns:
            Collection of result objects from the command
        Raises:
            PowerShellError: If the command produces any errors
        """
        self.pwsh.Commands.Clear()
        self.pwsh.Streams.Error.Clear()
        self.pwsh.Commands.AddScript(cmd)
        result = self.pwsh.Invoke()

        if self.pwsh.HadErrors:
            raise PowerShellError(self.pwsh.Streams.Error)

        return result

    def format_output(self, target: Collection[PSObject]) -> str:
        """
        Format PowerShell output as they would appear in a PowerShell console.
        Args:
            target: Collection of objects returned from execute_command()
        Returns:
            Formatted output string
        """
        if not target:
            return ""

        self.pwsh.Commands.Clear()
        self.pwsh.Streams.Error.Clear()
        self.pwsh.Commands.AddCommand("Out-String")
        formatted = self.pwsh.Invoke(target)

        if self.pwsh.HadErrors:
            raise PowerShellError(self.pwsh.Streams.Error)

        return "".join(str(obj) for obj in formatted)

    def get_property(self, target: Collection[PSObject], property: str) -> Any:
        """
        Extract a specific property value from the first PowerShell output object.
        Args:
            target: Collection of PowerShell output objects from execute_command()
            property: Name of the property which value should be retrieved
        Returns:
            Property value
        """
        return target[0].Properties[property].Value

    def get_str_property(self, target: Collection[PSObject], property: str) -> str:
        """
        Extract a specific property value from the first PowerShell output object in human-readable format.
        Args:
            target: Collection of PowerShell output objects from execute_command()
            property: Name of the property which value should be retrieved
        Returns:
            Property value
        """
        self.pwsh.Commands.Clear()
        self.pwsh.Streams.Error.Clear()
        self.pwsh.Commands.AddCommand("Select-Object").AddParameter("ExpandProperty", property)

        results = self.pwsh.Invoke(target.Items)

        if self.pwsh.HadErrors:
            raise PowerShellError(self.pwsh.Streams.Error)

        return str(results[0])
