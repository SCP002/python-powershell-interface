#! /usr/bin/env uv run

import powershell


def main() -> None:
    with powershell.PowerShell() as pwsh:
        proc = pwsh.execute_command("Get-Process -Name explorer")
        id = pwsh.get_str_property(proc, "Id")
        print(f"Explorer process ID: {id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
    finally:
        print("Press <Enter> to exit...")
        input()
