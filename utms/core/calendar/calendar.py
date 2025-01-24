from utms.resolvers import CalendarResolver
from utms.utils import TimeRange, get_logger

from .calendar_calculator import CalendarCalculator
from .calendar_data import CalendarState, MonthData, YearData
from .calendar_printer import CalendarPrinter, PrinterContext
from .registry import CalendarRegistry
from .unit_accessor import UnitAccessor

_resolver = CalendarResolver()
logger = get_logger("core.calendar.calendar")


class Calendar:
    def __init__(self, name, timestamp):
        logger.debug("Initializing calendar %s", name)
        self.name = name
        self.timestamp = timestamp
        units = CalendarRegistry.get_calendar_units(name)
        self._units = UnitAccessor(units)

        self._calculator = CalendarCalculator()

        self._state = self._create_calendar_state()
        self._printer = self._create_printer()
        logger.info("Calendar %s initialized successfully", name)

    def _create_calendar_state(self) -> CalendarState:
        """Create initial calendar state."""
        week_length = self.week_unit.get_value("length", self.timestamp) // self.day_unit.get_value(
            "length", self.timestamp
        )
        today_start = self.day_unit.get_value("start", self.timestamp)
        current_week_range = self._calculator.calculate_time_range(self.timestamp, self.week_unit)
        current_month_range = self._calculator.calculate_time_range(self.timestamp, self.month_unit)

        return CalendarState(
            name=self.name,
            timestamp=self.timestamp,
            week_length=week_length,
            today_start=today_start,
            current_week_range=current_week_range,
            current_month_range=current_month_range,
            units=self._units.get_all(),
        )

    def _create_printer(self) -> CalendarPrinter:
        """Create printer with appropriate context."""
        printer_context = PrinterContext(
            week_length=self._state.week_length,
            current_week_range=self._state.current_week_range,
            current_month_range=self._state.current_month_range,
            today_start=self._state.today_start,
        )
        return CalendarPrinter(printer_context)

    def get_time_range(self, timestamp, unit):
        start = unit.get_value("start", timestamp)
        end = start + unit.get_value("length", timestamp)
        return TimeRange(start, end)

    def print_year_calendar(self):
        year_data = self._calculator.calculate_year_data(self.timestamp, self.year_unit)
        self._print_year(year_data)

    def _print_year(self, year_data: YearData) -> None:
        self._printer.print_year_header(year_data)
        current_month = 1
        while True:
            if not self._print_month_group(year_data, current_month):
                break
            current_month += year_data.months_across
            print()

    def _print_month_group(self, year_data: YearData, current_month: int) -> bool:
        month_data = self._get_month_group_data(year_data, current_month)
        if not month_data.month_starts:
            return False

        self._print_month_group_headers(year_data, current_month, month_data)
        self._print_month_group_weeks(month_data)
        return True

    def _get_month_group_data(self, year_data: YearData, current_month: int) -> MonthData:
        return self._calculator.calculate_month_data(
            year_data.year_start,
            current_month,
            year_data.months_across,
            self._units,
            self.timestamp,
        )

    def _print_month_group_headers(
        self, year_data: YearData, current_month: int, month_data: MonthData
    ) -> None:
        self._printer.print_month_headers(
            year_data.year_start,
            current_month,
            year_data.months_across,
            self.year_unit.get_value("names"),
            self.month_unit,
        )

        self._printer.print_weekday_headers(
            year_data.months_across,
            month_data.month_starts,
            self.week_unit.get_value("names"),
        )

    def _print_month_group_weeks(self, month_data: MonthData) -> None:
        max_weeks = self._calculator.calculate_max_weeks(
            month_data, self.day_unit.get_value("length", self.timestamp), self.week_length
        )
        for _ in range(max_weeks):
            self._printer.print_week_row(
                month_data, self.day_unit.get_value("length", self.timestamp)
            )
            self._calculator.reset_first_day_weekdays(
                month_data, self.day_unit.get_value("length", self.timestamp)
            )

    def __str__(self) -> str:
        """String representation of the Calendar.

        Shows calendar name, current ranges, and available units.
        """
        unit_info = ", ".join(
            f"{unit_type}: {unit.name}"
            for unit_type, unit in self._units.items()
            if unit_type != "day_of_week_fn"
        )

        return (
            f"Calendar('{self.name}', " f"week: {self.week_length} days, " f"units: [{unit_info}])"
        )

    def __repr__(self) -> str:
        """Detailed representation of the Calendar."""
        return (
            f"Calendar(name='{self.name}', "
            f"timestamp={self.timestamp}, "
            f"week_length={self.week_length}, "
            f"today_start={self.today_start}, "
            f"week_range={self.current_week_range}, "
            f"month_range={self.current_month_range})"
        )

    @property
    def year_unit(self):
        return self._units.year

    @property
    def month_unit(self):
        return self._units.month

    @property
    def week_unit(self):
        return self._units.week

    @property
    def day_unit(self):
        return self._units.day

    @property
    def week_length(self) -> int:
        """Get week length from state."""
        return self._state.week_length

    @property
    def today_start(self) -> float:
        """Get today's start timestamp from state."""
        return self._state.today_start

    @property
    def current_week_range(self) -> TimeRange:
        """Get current week range from state."""
        return self._state.current_week_range

    @property
    def current_month_range(self) -> TimeRange:
        """Get current month range from state."""
        return self._state.current_month_range
