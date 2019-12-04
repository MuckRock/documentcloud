# Django
from django.test import TestCase

# Standard Library
import os
import re

# Local
from .report_generator import ReportGenerator


def convert(name: str) -> str:
    string = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    result = re.sub("([a-z0-9])([A-Z])", r"\1_\2", string).lower()
    return re.sub("_test$", "", result)


def normalize(name: str) -> str:
    return " ".join([n.capitalize() for n in name.split("_")])


base_dir = os.path.dirname(os.path.abspath(__file__))
reports = os.path.join(base_dir, "reports")


class ReportTestCase(TestCase):
    report_generator: ReportGenerator

    @classmethod
    def setUpClass(cls) -> None:
        name = convert(cls.__name__)
        super().setUpClass()
        cls.report_generator = ReportGenerator(os.path.join(reports, f"{name}.html"))
        cls.report_generator.add_heading(f"{normalize(name)} Tests")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.report_generator.close()
        super().tearDownClass()
