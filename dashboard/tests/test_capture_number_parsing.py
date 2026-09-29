from django.test import SimpleTestCase

from dashboard.services.capture_import import _number


class CaptureNumberParsingTests(SimpleTestCase):
    def test_numeric_formats(self):
        self.assertAlmostEqual(_number("2,3597"), 2.3597)
        self.assertAlmostEqual(_number("1.234,56"), 1234.56)
        self.assertAlmostEqual(_number("1234.56"), 1234.56)
