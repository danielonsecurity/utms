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


from ..loaders.event_loader import initialize_events, parse_event_definitions
from ..resolvers import (
    AnchorResolver,
    ConfigResolver,
    FixedUnitResolver,
    HyAST,
    VariableResolver,
    evaluate_hy_file,
)
from ..utils import format_hy_value, get_logger, get_ntp_date, hy_to_python, set_log_level
from ..utms_types import (
    AnchorManagerProtocol,
    ConfigData,
    ConfigPath,
    ConfigProtocol,
    ConfigValue,
    FixedUnitManagerProtocol,
    HyProperty,
    NestedConfig,
    OptionalString,
    is_expression,
)
from . import constants
from .managers.anchor import AnchorManager
from .events import EventManager
from .loaders.base import LoaderContext
from .loaders.variable import VariableLoader
from .managers.fixed_unit import FixedUnitManager
from .managers.variable import VariableManager

logger = get_logger("core.config")


class Config(ConfigProtocol):
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
        self._utms_dir = appdirs.user_config_dir(constants.APP_NAME, constants.COMPANY_NAME)
        # Ensure the config directory exists
        os.makedirs(self.utms_dir, exist_ok=True)
        self.init_resources()
        self._ast_manager = HyAST()
        self._data: NestedConfig = {}  # = self.load()

        self.resolver = ConfigResolver()
        self._variable_resolver = VariableResolver
        self._variables = {}
        self._variable_manager = VariableManager()
        self._load_variables()
        self._load_hy_config()
        set_log_level(self.loglevel)
        self._fixed_units: FixedUnitManagerProtocol = FixedUnitManager()
        self._calendar_units = {}
        self._calendars = {}
        self._anchors = AnchorManager()
        self._anchors._units = self.units

        self._load_fixed_units()
        self._load_calendar_units()
        self._load_anchors()
        self._event_manager = EventManager()
        self._load_events()

    def _load_hy_config(self) -> None:
        config_hy = os.path.join(self.utms_dir, "config.hy")
        if os.path.exists(config_hy):
            try:
                expressions = evaluate_hy_file(config_hy)
                if expressions:
                    config = self.resolver.resolve_config_property(expressions[0])
                    self._data = config
            except Exception as e:
                logger.error("Error loading Hy config: %s", e)

    def _save_hy_config(self) -> None:
        """Save current configuration to config.hy."""
        config_hy = os.path.join(self.utms_dir, "config.hy")

        settings = []
        for key, value in self._data.items():
            formatted_value = format_hy_value(value)
            settings.append(f"  '({key} {formatted_value})")

        content = [
            ";; This file is managed by UTMS - do not edit manually",
            "(custom-set-config",
            *sorted(settings),
            ")",
        ]

        with open(config_hy, "w") as f:
            f.write("\n".join(content))

    def get_value(self, key: ConfigPath, pretty: bool = False) -> ConfigValue:
        """Get value from configuration."""
        value = self._data.get(key)

        if value is not None:
            value = hy_to_python(value)

        if pretty and value is not None:
            return json.dumps(value, indent=4, sort_keys=True)

        return value

    def has_value(self, key: ConfigPath) -> bool:
        return key in self._data

    def set_value(self, key: ConfigPath, value: ConfigValue) -> None:
        self._data[key] = value
        self._save_hy_config()

    def print(self, filter_key: OptionalString = None) -> None:
        if filter_key:
            try:
                pretty_result = self.get_value(filter_key, pretty=True)
                print(pretty_result)
            except KeyError as e:
                print(f"Error: {e}")
        else:
            print(json.dumps(self.data, indent=4, sort_keys=True))

    def _load_variables(self) -> None:
        variables_hy = os.path.join(self.utms_dir, "variables.hy")
        if os.path.exists(variables_hy):
            try:
                # Create loader with manager
                loader = VariableLoader(self._variable_manager)

                # Parse file into nodes
                ast_manager = HyAST()
                nodes = ast_manager.parse_file(variables_hy)

                # Create context
                context = LoaderContext(
                    config_dir=self.utms_dir,
                    variables=self._variables,  # Pass any existing variables
                )

                # Process nodes
                variables = loader.process(nodes, context)

                # Update internal state
                self._variables = {
                    name: HyProperty(value=var.value, original=var.original)
                    for name, var in variables.items()
                }

            except Exception as e:
                logger.error(f"Error loading variables: {e}")
                raise

    def save_variables(self) -> None:
        variables_hy = os.path.join(self.utms_dir, "variables.hy")
        self._variable_manager.save(variables_hy)

    def _load_events(self) -> None:
        events_file = os.path.join(self.utms_dir, "events.hy")
        if os.path.exists(events_file):
            try:
                event_expressions = evaluate_hy_file(events_file)
                if event_expressions:
                    parsed_event_defs = parse_event_definitions(event_expressions)
                    logger.debug("Parsed event definitions %s", parsed_event_defs)
                    event_instances = initialize_events(parsed_event_defs, self._variables)
                    logger.debug("Created event instances %s", event_instances)
                    for event in event_instances.values():
                        logger.debug("Adding event %s", event.name)
                        self._event_manager.add_event(event)
            except Exception as e:
                logger.error("Error loading events: %s", e)

    def init_resources(self) -> None:
        """Copy resources to the user config directory if they do not already
        exist."""
        resources = [
            "system_prompt.txt",
            "calendar_units.hy",
            "fixed_units.hy",
            "events.hy",
        ]
        for item in resources:
            source_file = importlib.resources.files("utms.resources") / item
            destination_file = os.path.join(self.utms_dir, item)

            # Copy only if the destination file does not exist
            if not os.path.exists(destination_file):
                shutil.copy(str(source_file), destination_file)

    def _load_anchors(self) -> None:
        anchors_file = os.path.join(self.utms_dir, "anchors.hy")
        if os.path.exists(anchors_file):
            try:
                nodes = self._ast_manager.parse_file(anchors_file)
                variables_dict = {name: prop.value for name, prop in self._variables.items()}
                anchor_instances = process_anchors(nodes, variables_dict)
                for anchor in anchor_instances.values():
                    self._anchors.add_anchor(anchor)
            except Exception as e:
                logger.error(f"Error loading anchors: {e}")
                raise

    def _load_anchors(self) -> None:
        """Load anchors from anchors.hy"""
        anchors_file = os.path.join(self.utms_dir, "anchors.hy")
        if os.path.exists(anchors_file):
            try:
                # Create loader with manager
                from .loaders.anchor import AnchorLoader
                loader = AnchorLoader(self._anchors)

                # Parse file into nodes
                nodes = self._ast_manager.parse_file(anchors_file)

                # Create context with variables
                from .loaders.base import LoaderContext
                variables = {}

                for name, var in self._variables.items():
                    if isinstance(var, HyProperty):
                        variables[name] = var.value
                    else:
                        variables[name] = var
                    # Also add underscore version for compatibility
                    variables[name.replace("-", "_")] = variables[name]
                
                context = LoaderContext(
                    config_dir=self.utms_dir,
                    variables=variables,
                )

                # Process nodes using loader
                loader.process(nodes, context)

            except Exception as e:
                logger.error(f"Error loading anchors: {e}")
                raise



    def save_anchors(self) -> None:
        """Save anchors to file."""
        anchors_file = os.path.join(self.utms_dir, "anchors.hy")
        self._anchors.save(anchors_file)

    def _load_fixed_units(self) -> None:
        """Load fixed units from fixed_units.hy"""
        fixed_units_file = os.path.join(self.utms_dir, "fixed_units.hy")
        if os.path.exists(fixed_units_file):
            try:
                # Create and initialize the manager
                self._fixed_units = FixedUnitManager()

                # Parse and load the units
                nodes = self._ast_manager.parse_file(fixed_units_file)

                # Create loader with manager
                from ..core.loaders.fixed_unit import FixedUnitLoader

                loader = FixedUnitLoader(self._fixed_units)

                # Create context with variables
                from ..core.loaders.base import LoaderContext

                context = LoaderContext(config_dir=self.utms_dir, variables=self._variables)

                # Process nodes
                loader.process(nodes, context)

            except Exception as e:
                logger.error(f"Error loading fixed units: {e}")
                raise


    def save_fixed_units(self):
        units_file = os.path.join(self.utms_dir, "fixed_units.hy")
        self.units.save(units_file)

    def _load_calendar_units(self) -> None:
        units_hy = os.path.join(self.utms_dir, "calendar_units.hy")

        if os.path.exists(units_hy):
            try:
                expressions = evaluate_hy_file(units_hy)
                parsed_calendar_units = parse_unit_definitions(expressions)
                calendar_units = initialize_units(parsed_calendar_units)
                calendars = parse_calendar_definitions(expressions)
                resolve_unit_properties(calendar_units)
                self._calendar_units = calendar_units
                self._calendars = calendars
                logger.info("Loaded calendar units from Hy file")
            except Exception as e:
                logger.error("Error loading calendar units: %s", e)

    @property
    def utms_dir(self) -> str:
        return str(self._utms_dir)

    @property
    def data(self) -> ConfigData:
        return self._data

    @property
    def units(self) -> FixedUnitManagerProtocol:
        return self._fixed_units

    @property
    def anchors(self) -> AnchorManagerProtocol:
        return self._anchors

    @property
    def loglevel(self):
        return self.get_value("loglevel")

    @property
    def events(self) -> EventManager:
        return self._event_manager
