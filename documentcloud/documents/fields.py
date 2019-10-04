# Django
from rest_framework import serializers


class ChoiceField(serializers.ChoiceField):
    """Choice field enhanced to use the choices label and ability to omit choices"""

    def __init__(self, choices, **kwargs):
        choices = [
            (choice.value, label)
            for label, choice in choices._fields.items()
            if choice.api
        ]
        self.choice_map = {label: value for value, label in choices}
        super().__init__(choices, **kwargs)

    def to_representation(self, value):
        if value in ("", None):
            return value
        return self.choices.get(value, value)

    def to_internal_value(self, data):
        if data == "" and self.allow_blank:
            return ""

        try:
            return self.choice_map[str(data)]
        except KeyError:
            self.fail("invalid_choice", input=data)
