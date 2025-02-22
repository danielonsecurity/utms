"""This module defines the `Config` class, which manages the configuration of
time units and datetime anchors.

The `Config` class is responsible for populating predefined time units and datetime anchors.  It
uses the `UnitManager` class to manage time units such as Planck Time, Picoseconds, and
Milliseconds, and the `AnchorManager` class to manage datetime anchors like Unix Time, CE Time, and
Big Bang Time.

Constants from the `constants` module are used to define the values for the time units and anchors.

Modules:
- `utms.constants`: Contains predefined constants for time and datetime values.
- `utms.anchors`: Contains the `AnchorManager` class for managing datetime anchors.
- `utms.units`: Contains the `UnitManager` class for managing time units.

Usage:
- Instantiate the `Config` class to initialize the units and anchors with predefined values.
"""

import importlib.resources
import json
import os
import re
import shutil
import socket
import sys
from datetime import datetime, timezone
from decimal import Decimal
from time import time
from typing import Any, List, Optional, Tuple, Union

import appdirs
import ntplib

from utms import constants
from utms.anchors import AnchorConfig, AnchorManager
from utms.units import UnitManager


def get_ntp_date() -> datetime:
    """Retrieves the current date in datetime format using an NTP (Network Time
    Protocol) server.

    This function queries an NTP server (default is "pool.ntp.org") to
    get the accurate current time. The NTP timestamp is converted to a
    UTC `datetime` object and formatted as a date string. If the NTP
    request fails (due to network issues or other errors), the function
    falls back to the system time.

    Returns:
        str: The current date in 'YYYY-MM-DD' format, either from the
        NTP server or the system clock as a fallback.

    Exceptions:
        - If the NTP request fails, the system time is used instead.
    """
    client = ntplib.NTPClient()
    try:
        # Query the NTP server
        response = client.request("pool.ntp.org", version=3)
        ntp_timestamp = float(response.tx_time)
    except (ntplib.NTPException, socket.error, OSError) as e:
        print(f"Error fetching NTP time: {e}", file=sys.stderr)
        ntp_timestamp = float(time())  # Fallback to system time

    # Convert the timestamp to a UTC datetime and format as 'YYYY-MM-DD'
    current_date = datetime.fromtimestamp(ntp_timestamp, timezone.utc)
    return current_date


class Config:
    """Configuration class that manages units and anchors for time and datetime
    references.

    This class is responsible for populating time units and datetime anchors based on predefined
    constants.  It uses the `AnchorManager` and `UnitManager` classes to add relevant time units and
    datetime anchors.
    """

    def __init__(self) -> None:
        """Initializes the configuration by creating instances of
        `AnchorManager` and `UnitManager`, then populating them with units and
        anchors.

        This method calls `populate_units()` to add time units and
        `populate_anchors()` to add datetime anchors.
        """
        self.utms_dir = appdirs.user_config_dir(constants.APP_NAME, constants.COMPANY_NAME)
        # Ensure the config directory exists
        os.makedirs(self.utms_dir, exist_ok=True)
        self.init_resources()
        self.data: Any = self.load()

        self.units = UnitManager()
        self.anchors = AnchorManager(self.units)
        self.load_units()
        self.populate_dynamic_anchors()
        self.load_anchors()

    def _parse_key(self, key: str) -> List[Union[str, int]]:
        """Parse a dot-separated key with support for array indices.

        :param key: The key to parse (e.g.,
            'gemini.available_models[1]').
        :return: A list of keys and indices to traverse.
        """
        pattern = re.compile(r"(\w+)|\[(\d+)\]")
        return [int(match[1]) if match[1] else match[0] for match in pattern.findall(key)]

    def _traverse(self, key: str) -> Tuple[Any, Union[str, int]]:
        """Traverse the configuration using a parsed key.

        :param key: The dot-separated key (e.g.,
            'gemini.available_models[1]').
        :return: The parent object and the last key/index.
        """
        keys = self._parse_key(key)
        current = self.data

        for part in keys[:-1]:
            if isinstance(part, int):  # Array index
                if not isinstance(current, list) or part >= len(current):
                    raise KeyError(f"Array index {part} out of range.")
                current = current[part]
            else:  # Dictionary key
                if part not in current:
                    raise KeyError(f"Key '{part}' does not exist.")
                current = current[part]

        return current, keys[-1]

    def init_resources(self) -> None:
        """Copy resources to the user config directory if they do not already
        exist."""
        resources = ["system_prompt.txt", "config.json", "anchors.json", "units.json"]
        for item in resources:
            source_file = importlib.resources.files("utms.resources") / item
            destination_file = os.path.join(self.utms_dir, item)

            # Copy only if the destination file does not exist
            if not os.path.exists(destination_file):
                shutil.copy(str(source_file), destination_file)

    def load(self) -> Any:
        """Load the configuration from the JSON file.

        Returns:
            dict: Configuration data.
        """

        config_file = os.path.join(self.utms_dir, "config.json")

        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    # Function to save the configuration to the JSON file
    def save(self) -> None:
        """Save the configuration data to the JSON file.

        Args:
            config (dict): Configuration data to be saved.
        """
        config_file = os.path.join(self.utms_dir, "config.json")

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)

    def load_anchors(self) -> None:
        """Loads anchors from the 'anchors.json' file and populates the anchors
        dynamically.

        This method reads the `anchors.json` file, parses its content, and uses the `AnchorManager`
        to add each anchor to the configuration.
        """
        anchors_file = os.path.join(self.utms_dir, "anchors.json")

        if os.path.exists(anchors_file):
            with open(anchors_file, "r", encoding="utf-8") as f:
                anchors_data = json.load(f)

            # Iterate through the anchors data and add each anchor
            for key, anchor in anchors_data.items():
                name = anchor.get("name")
                timestamp = anchor.get("timestamp")
                groups = anchor.get("groups")
                precision = anchor.get("precision")
                breakdowns = anchor.get("breakdowns")
                # Add anchor using the details loaded from the JSON
                anchor_config = AnchorConfig(
                    label=key,
                    name=name,
                    value=Decimal(timestamp),
                    groups=groups,
                    precision=Decimal(precision) if precision else None,
                    breakdowns=breakdowns,
                )
                self.anchors.add_anchor(anchor_config)

        else:
            print(f"Error: '{anchors_file}' not found.")

    def save_anchors(self) -> None:
        """Saves the current anchors to the 'anchors.json' file.

        This method serializes the anchors stored in the `self.anchors` set
        and writes them to the `anchors.json` file.
        """
        anchors_file = os.path.join(self.utms_dir, "anchors.json")
        anchors_data = {}

        # Iterate through each anchor and prepare data for saving
        for anchor in self.anchors:
            anchor_info = {
                "name": anchor.name,
                "timestamp": float(anchor.value),
                "groups": anchor.groups,
                "precision": float(anchor.precision) if anchor.precision else None,
                "breakdowns": anchor.breakdowns,
            }
            anchors_data[anchor.label] = anchor_info

        # Write the serialized anchors data to the file
        try:
            with open(anchors_file, "w", encoding="utf-8") as f:
                json.dump(anchors_data, f, ensure_ascii=False, indent=4)
            print(f"Anchors successfully saved to '{anchors_file}'")
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"Error saving anchors: {e}")
        except json.JSONDecodeError as e:
            print(f"Error serializing data to JSON: {e}")

    def load_units(self) -> None:
        """Loads time units from the 'units.json' file and populates the units
        dynamically.

        This method reads the `units.json` file, parses its content, and uses the `UnitManager`
        to add each unit to the configuration.
        """
        units_file = os.path.join(self.utms_dir, "units.json")

        if os.path.exists(units_file):
            with open(units_file, "r", encoding="utf-8") as f:
                units_data = json.load(f)

            # Iterate through the units data and add each unit
            for key, unit in units_data.items():
                name = unit.get("name")
                value = unit.get("value")
                # Add unit using the details loaded from the JSON
                self.units.add_unit(name, key, Decimal(value))

        else:
            print(f"Error: '{units_file}' not found.")

    def save_units(self) -> None:
        """Saves the current time units to the 'units.json' file.

        This method serializes the time units stored in the `self.units` instance
        and writes them to the `units.json` file.
        """
        units_file = os.path.join(self.utms_dir, "units.json")
        units_data = {}

        # Iterate through each unit and prepare data for saving
        for unit_abbreviation in self.units:
            unit = self.units[unit_abbreviation]
            units_data[unit_abbreviation] = {
                "name": unit.name,
                "symbol": unit_abbreviation,  # or another property if you have one
                "value": str(unit.value),
            }
        # Write the serialized units data to the file
        try:
            with open(units_file, "w", encoding="utf-8") as f:
                json.dump(units_data, f, ensure_ascii=False, indent=4)
            print(f"Units successfully saved to '{units_file}'")
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"Error saving units: {e}")
        except json.JSONDecodeError as e:
            print(f"Error serializing data to JSON: {e}")

    def get_value(self, key: str, pretty: bool = False) -> Union[Any, str]:
        """Get the value from the configuration by key.

        :param key: The dot-separated key (e.g.,
            'gemini.available_models[1]').
        :param pretty: If True, return the value formatted as pretty
            JSON.
        :return: The value at the specified key.
        """
        current, last_key = self._traverse(key)

        # Handle array index or dictionary key
        if isinstance(last_key, int):  # Array index
            if not isinstance(current, list) or last_key >= len(current):
                raise KeyError(f"Array index {last_key} out of range.")
            result = current[last_key]
        else:
            result = current[last_key]

        if pretty:
            return json.dumps(result, indent=4, sort_keys=True)
        return result

    def has_value(self, key: str) -> bool:
        """Checks whether a nested key exists in the configuration and its
        value is not None.

        :param key: The dot-separated key path (e.g., 'gemini.api_key').
        :return: True if the key exists and its value is not None, False
            otherwise.
        """
        try:
            current, last_key = self._traverse(key)

            # Handle array index or dictionary key
            if isinstance(last_key, int):  # Array index
                return (
                    isinstance(current, list)
                    and 0 <= last_key < len(current)
                    and current[last_key] is not None
                )
            return last_key in current and current[last_key] is not None
        except KeyError:
            return False

    def set_value(self, key: str, value: Any) -> None:
        """Set a value in the configuration by key.

        :param key: The dot-separated key (e.g.,
            'gemini.available_models[1]').
        :param value: The value to set.
        """
        current, last_key = self._traverse(key)
        if isinstance(last_key, int):  # Array index
            if not isinstance(current, list) or last_key >= len(current):
                raise KeyError(f"Array index {last_key} out of range.")
            current[last_key] = value
        else:
            current[last_key] = value
        print(f"Configuration for '{key}' updated to '{value}'")

        # Check if the '_choices' field exists and append the new value if not already present
        choices_key = f"{key}_choices"
        if self.has_value(choices_key):
            # Get the current choices list
            choices = self.get_value(choices_key)
            if isinstance(choices, list):
                # Only append if the value doesn't already exist in the list
                if value not in choices:
                    choices.append(value)

        self.save()

    def print(self, filter_key: Optional[str] = None) -> None:
        """
        Print the configuration in a formatted JSON style.

        Optionally filters the output to display the value of a specific key path.

        Parameters
        ----------
        filter_key : str, optional
            A dot-separated key path to filter the config output (e.g., 'gemini.api_key').
            If provided, only the value of the specified key will be printed. If the key
            points to a nested dictionary or list, its content is displayed in a
            formatted manner.

        Returns
        -------
        None

        Raises
        ------
        KeyError
            If the provided key path is invalid or does not exist in the configuration.
        """
        if filter_key:
            try:
                pretty_result = self.get_value(filter_key, pretty=True)
                print(pretty_result)
            except KeyError as e:
                print(f"Error: {e}")
        else:
            print(json.dumps(self.data, indent=4, sort_keys=True))

    def select_from_choices(self, key: str) -> Any:
        """
        Allow interactive selection for configuration parameters with a '_choices' field.

        If the specified configuration key has an associated '_choices' field, this method
        displays the available options and prompts the user to select one. The selected
        value is then set as the new value for the key. If no '_choices' field is found,
        the current value of the key is returned.

        Parameters
        ----------
        key : str
            The dot-separated key to check (e.g., 'gemini.model').

        Returns
        -------
        Any
            The selected value from the available choices, or the current value if no
            choices are available. Returns `None` if the user does not make a choice.

        Raises
        ------
        ValueError
            If the '_choices' field is not a list.
        """
        # Get the base config value and choices (if any)
        current, last_key = self._traverse(key)

        # Check if '_choices' field exists
        choices_key = f"{key}_choices"
        if self.has_value(choices_key):
            # Get the list of available choices
            choices = self.get_value(choices_key)

            if isinstance(choices, list):
                print(f"Available choices for '{key}':")
                for idx, choice in enumerate(choices, 1):
                    print(f"{idx}. {choice}")

                # Prompt user for a choice
                while True:
                    try:
                        user_choice = input(f"Select a choice (1-{len(choices)}): ")
                        if not user_choice:
                            return None  # Explicit return of None if no choice is made
                        if 1 <= int(user_choice) <= len(choices):
                            selected_value = choices[int(user_choice) - 1]
                            # Set the selected value in the config
                            self.set_value(key, selected_value)
                            return selected_value
                        print("Invalid choice. Please try again.")
                    except ValueError:
                        print("Invalid input. Please enter a number.")
            else:
                raise ValueError(f"Invalid '_choices' format for '{key}'. Expected a list.")
        else:
            print(f"No choices available for '{key}'.")
            return current[last_key]  # No choices, return the current value

    def select_from_list(self, source_key: str, target_key: str, index: int) -> None:
        """
        Assign an element from a JSON array to a target key in the configuration.

        This method retrieves an element from a list at the specified source key
        and assigns it to the target key in the configuration. The element is
        identified by its index in the list.

        Parameters
        ----------
        source_key : str
            The dot-separated key path of the source list (e.g., 'gemini.available_models').
        target_key : str
            The dot-separated key path of the destination (e.g., 'gemini.model').
        index : int
            The index of the element to select from the list.

        Raises
        ------
        KeyError
            If the source or target key paths are invalid.
        ValueError
            If the source key does not refer to a list or the index is out of range.
        """
        # Get the source list
        source_list = self.get_value(source_key)
        if not isinstance(source_list, list):
            raise ValueError(f"Source key '{source_key}' must refer to a list.")

        # Find the selected element
        if index < 0 or index >= len(source_list):
            raise ValueError(f"Index {index} is out of range for list at '{source_key}'.")
        selected_value = source_list[index]

        # Set the selected value in the target key
        self.set_value(target_key, selected_value)

    def select_from_list_interactive(self, source_key: str, target_key: str) -> None:
        """
        Prompt the user to select an element from a JSON array interactively.

        This method retrieves a list from the specified source key, displays the
        available elements to the user, and prompts them to select one by index.
        The selected element is then assigned to the target key in the configuration.

        Parameters
        ----------
        source_key : str
            The dot-separated key path of the source list (e.g., 'gemini.available_models').
        target_key : str
            The dot-separated key path of the destination (e.g., 'gemini.model').

        Raises
        ------
        KeyError
            If the source or target key paths are invalid.
        ValueError
            If the source key does not refer to a list.
        """
        source_list = self.get_value(source_key)
        if not isinstance(source_list, list):
            raise ValueError(f"Source key '{source_key}' must refer to a list.")

        print(f"Choose an element from the list at '{source_key}':")
        for i, item in enumerate(source_list):
            print(f"{i}: {item}")

        while True:
            try:
                index = int(input("Enter the index of the element to select: "))
                if 0 <= index < len(source_list):
                    break
                print(f"Invalid index. Must be between 0 and {len(source_list) - 1}.")
            except ValueError:
                print("Invalid input. Please enter a valid index.")

        self.set_value(target_key, source_list[index])

    def populate_dynamic_anchors(self) -> None:
        """Populates the `AnchorManager` instance with predefined datetime
        anchors.

        This method adds various datetime anchors such as Unix Time, CE Time, and Big Bang Time,
        using the `add_datetime_anchor` and `add_decimal_anchor` methods of the `AnchorManager`
        instance.  Each anchor is added with its name, symbol, and corresponding datetime value.
        """

        self.anchors.add_anchor(
            AnchorConfig(
                label="NT",
                name=f"Now Time ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})",
                value=get_ntp_date(),
                groups=["default", "dynamic", "modern"],
            )
        )
        self.anchors.add_anchor(
            AnchorConfig(
                label="DT",
                name=f"Day Time ({datetime.now().strftime('%Y-%m-%d 00:00:00')})",
                value=datetime(
                    datetime.now().year,
                    datetime.now().month,
                    datetime.now().day,
                    tzinfo=datetime.now().astimezone().tzinfo,
                ),
                breakdowns=[["dd", "cd", "s", "ms"], ["h", "m", "s", "ms"], ["KS", "s", "ms"]],
                groups=["dynamic", "modern"],
            )
        )
        self.anchors.add_anchor(
            AnchorConfig(
                label="MT",
                name=f"Month Time ({datetime.now().strftime('%Y-%m-01 00:00:00')})",
                value=datetime(
                    datetime.now().year,
                    datetime.now().month,
                    1,
                    tzinfo=datetime.now().astimezone().tzinfo,
                ),
                breakdowns=[
                    ["d", "dd", "cd", "s", "ms"],
                    ["w", "d", "dd", "cd", "s", "ms"],
                    ["MS", "KS", "s", "ms"],
                ],
                groups=["dynamic", "modern"],
            )
        )

        self.anchors.add_anchor(
            AnchorConfig(
                label="YT",
                name=f"Year Time ({datetime.now().strftime('%Y-01-01 00:00:00')})",
                value=datetime(
                    datetime.now().year, 1, 1, tzinfo=datetime.now().astimezone().tzinfo
                ),
                breakdowns=[
                    ["d", "dd", "cd", "s", "ms"],
                    ["w", "d", "dd", "cd", "s", "ms"],
                    ["M", "d", "dd", "cd", "s", "ms"],
                    ["MS", "KS", "s", "ms"],
                ],
                groups=["dynamic", "modern"],
            )
        )
