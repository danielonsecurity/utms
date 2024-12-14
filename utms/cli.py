"""
This module implements a Command Line Interface (CLI) for the
Universal Time Measurement System (UTMS).  It allows users to
interactively input commands for time and date-related conversions,
resolving and displaying formatted timestamps based on their input.

**Key Features**:
1. **Interactive Shell**: Provides a command-line interface with input
   handling, autocompletion, and a stylish prompt for user commands.
2. **Command Handling**: The CLI supports specific commands like
   `.conv` for various conversion tables and dynamic date resolution.
3. **Date/Time Resolution**: The input can be processed to resolve
   specific dates or timestamps, including handling special terms like
   "yesterday", "tomorrow", or "now".
4. **Error Handling**: Gracefully handles invalid inputs and
   interruptions, providing helpful error messages to the user.

**Dependencies**:
- `prompt_toolkit`: A library for building interactive CLI
  applications, enabling features like autocompletion and input
  history.
- `utms.constants`: Includes version information and manager for
  conversion functionality.
- `utms.utils`: Contains utility functions like
  `get_current_time_ntp`, `print_results`, `print_time`, and
  `resolve_date`.

**Usage Example**:
```python
>>> main()
Welcome to UTMS CLI (Version 1.0.0)!
Current time: 2024-12-14T20:00:00+00:00
Prompt> .conv concise
"""

from datetime import datetime
from decimal import Decimal

from prompt_toolkit import ANSI, PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style

from utms.constants import VERSION, manager
from utms.utils import get_current_time_ntp, print_results, print_time, resolve_date

# Create a style for the shell
style = Style.from_dict({"prompt": "#ff6600 bold", "input": "#008800", "output": "#00ff00"})

# Define a simple WordCompleter (autocompletion for date formats, or any other completions)
completer = WordCompleter(
    ["yesterday", "tomorrow", "today", "now", "exit", ".conv"],
    ignore_case=True,
)

# History for command input
history = InMemoryHistory()

# Create the interactive session
session: PromptSession[str] = PromptSession(completer=completer, history=history, style=style)


def handle_input(input_text: str) -> None:
    """
    Processes the input text to execute a corresponding command based on the provided input.

    This function handles commands that start with `.conv` followed by a subcommand. The supported
    subcommands are:

    - **"concise"**: Calls the `print_concise_conversion_table` function.
    - **"new"**: Calls the `print_conversion_table` function.
    - **"old"**: Calls the `print_reversed_conversion_table` function.
    - **"."**: Calls the `print_all_conversions` function (default action).

    If the input does not match any subcommand, the function defaults to executing
    `print_all_conversions`.

    Args:
        input_text (str): The input string, typically a command prefixed with `.conv`.

    Returns:
        None: The function performs actions based on the input and does not return any value.
    """
    if input_text.startswith(".conv"):
        # Split the command to check arguments (if any)
        parts = input_text.split()
        if len(parts) == 2:  # .conv <subcommand>
            unit = parts[1]
            manager.print_conversion_table(unit)
        elif len(parts) == 3:
            unit = parts[1]
            columns = int(parts[2])
            manager.print_conversion_table(unit, columns)
        elif len(parts) == 4:
            unit = parts[1]
            columns = int(parts[2])
            rows = int(parts[3])
            manager.print_conversion_table(unit, columns, rows)
        else:
            manager.print_conversion_table("s")


def main() -> None:
    """
    Main entry point for the UTMS CLI (Universal Time Measurement System Command Line Interface).

    This function starts an interactive shell where the user can enter commands. The supported
    features include:

    - **Welcome Message**: Displays a message with the version of the CLI.
    - **User Input**: Prompts the user for input using `session.prompt("Prompt> ")`.
    - **Command Handling**:

      - **`.conv <subcommand>`**: Processes conversion commands via `handle_input`.
      - Resolves a date from input text and displays it using `print_time`.

    - **Exit Option**: Allows the user to exit the shell by typing "exit".
    - **Error Handling**: Catches invalid input or keyboard interrupts and gracefully prints
      appropriate error messages.

    The function runs in a loop until the user chooses to exit.

    Args:
        None: This function does not take any arguments.

    Returns:
        None: It operates interactively and performs actions based on user input without
              returning a value.
    """
    print(f"Welcome to UTMS CLI (Version {VERSION})!")
    print_time(get_current_time_ntp())
    while True:
        try:
            # Read user input
            input_text = session.prompt("Prompt> ")

            # Exit condition
            if input_text.lower() == "exit":
                print("Exiting shell...")
                break

            if input_text.startswith(".conv"):
                handle_input(input_text)
                continue

            # Resolve date from input text
            parsed_timestamp = resolve_date(input_text)

            # Ensure parsed_timestamp is a datetime before passing it to print_time
            if isinstance(parsed_timestamp, datetime):
                print_time(parsed_timestamp)
            elif isinstance(parsed_timestamp, Decimal):
                # Handle case where it's an integer (if applicable, convert to datetime)
                print(f"Resolved date (integer timestamp): {parsed_timestamp}")
                print_results(parsed_timestamp)

        except ValueError as e:
            # If the input is invalid, print the error message
            print_formatted_text(ANSI(f"[bold red]Error: {str(e)}[/bold red]"))
            continue
        except KeyboardInterrupt:
            continue
        except EOFError:
            print("\nExiting gracefully. Goodbye!")
            return