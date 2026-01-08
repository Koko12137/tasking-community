#!/usr/bin/env python3
"""Test cases for the xml extract_by_label function."""

import unittest
from tasking.utils.string.xml import extract_by_label


class TestXMLExtract(unittest.TestCase):
    """Test the extract_by_label function."""

    def test_extract_with_newlines(self):
        """Test extracting content with newlines in tags."""
        input_content = '<script_path>\n./02-SCRIPT/VLOG-SHOT-SCRIPT-日常生活记录-20240601.md\n</script_path>\n<target_app>\n抖音\n</target_app>'
        self.assertEqual(extract_by_label(input_content, 'script_path'), './02-SCRIPT/VLOG-SHOT-SCRIPT-日常生活记录-20240601.md')
        self.assertEqual(extract_by_label(input_content, 'target_app'), '抖音')

    def test_extract_without_newlines(self):
        """Test extracting content without newlines in tags."""
        input_content = '<script_path>./02-SCRIPT/VLOG-SHOT-SCRIPT-日常生活记录-20240601.md</script_path><target_app>抖音</target_app>'
        self.assertEqual(extract_by_label(input_content, 'script_path'), './02-SCRIPT/VLOG-SHOT-SCRIPT-日常生活记录-20240601.md')
        self.assertEqual(extract_by_label(input_content, 'target_app'), '抖音')

    def test_extract_with_attributes(self):
        """Test extracting content from tags with attributes."""
        input_content = '<script_path id="123" name="vlog">\n./file.md\n</script_path>'
        self.assertEqual(extract_by_label(input_content, 'script_path'), './file.md')

    def test_extract_multiple_labels(self):
        """Test extracting with multiple labels in priority order."""
        input_content = '<script_path>\n./file.md\n</script_path>'
        # Should find script_path first
        self.assertEqual(extract_by_label(input_content, 'script_path', 'file_path'), './file.md')
        # Should find file_path first if it exists
        input_content2 = '<file_path>/path/to/file.md</file_path>'
        self.assertEqual(extract_by_label(input_content2, 'script_path', 'file_path'), '/path/to/file.md')

    def test_extract_with_attributes_without_newlines(self):
        """Test extracting content from tags with attributes without newlines."""
        input_content = '<file_path class="test">/path/to/file.md</file_path>'
        self.assertEqual(extract_by_label(input_content, 'file_path'), '/path/to/file.md')

    def test_extract_empty_result(self):
        """Test extracting non-existent labels returns empty string."""
        input_content = '<script_path>\n./file.md\n</script_path>'
        self.assertEqual(extract_by_label(input_content, 'non_existent_label'), '')


if __name__ == '__main__':
    unittest.main()
