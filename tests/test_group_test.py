

from container_processing.group_test_parse import extract_summary_from_group_test_event
import pytest


@pytest.fixture
def sample_group_test():
    with open('tests/grades_test-1.json') as fin:
        return fin.read()


class TestGroupTest(object):

    def test_parse_sample(self, sample_group_test):

        data = extract_summary_from_group_test_event(sample_group_test)
        assert 'images' in data.keys()
        assert 'errata_id' in data.keys()
        assert 'message_id' in data.keys()
        assert len(data['images']) == 9
