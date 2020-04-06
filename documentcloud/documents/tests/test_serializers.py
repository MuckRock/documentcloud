# Third Party
import pytest

# DocumentCloud
from documentcloud.documents.serializers import DocumentSerializer


class TestDocumentSerializer:
    def test_good_data(self):
        """Test validating good value for `data`"""
        serializer = DocumentSerializer(data={"data": {"a": ["1"]}}, partial=True)
        assert serializer.is_valid()

    def test_good_data_auto_list(self):
        """Test automatically listing a single string in `data`"""
        serializer = DocumentSerializer(data={"data": {"a": "1"}}, partial=True)
        assert serializer.is_valid()
        assert serializer.validated_data["data"]["a"] == ["1"]

    @pytest.mark.parametrize("data", [["a"], {"a": {"b": 1}}, {"a": ["1", [2]]}])
    def test_bad_data(self, data):
        serializer = DocumentSerializer(data={"data": data}, partial=True)
        assert not serializer.is_valid()
