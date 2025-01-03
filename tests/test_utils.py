import unittest
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch

from utms.config import Config
from utms.utils import print_time

local_timezone = datetime.now().astimezone().tzinfo
config = Config()


class TestPrintFunction(unittest.TestCase):
    @patch("sys.stdout", new_callable=StringIO)
    def test_prints_time_ntp(self, mock_stdout):
        print_time(datetime(1950, 1, 1, 0, 0, tzinfo=timezone.utc), config)
        output = mock_stdout.getvalue()
        self.assertTrue(output.strip(), "Function did not print anything!")


if __name__ == "__main__":
    unittest.main()
