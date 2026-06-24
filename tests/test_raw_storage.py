import os
import unittest
import tempfile
import shutil
import json
from storage import RawStorage

class TestRawStorage(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for tests
        self.test_dir = tempfile.mkdtemp()
        self.storage = RawStorage(base_dir=self.test_dir)

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    def test_save_raw_string(self):
        content = "Hello, world!"
        saved_path = self.storage.save_raw("test_source", "test_file.txt", content)
        
        self.assertTrue(os.path.exists(saved_path))
        with open(saved_path, 'r', encoding='utf-8') as f:
            read_content = f.read()
        self.assertEqual(read_content, content)

    def test_save_raw_dict(self):
        content = {"message": "Hello, world!", "status": 200}
        saved_path = self.storage.save_raw("test_source", "test_file.json", content)
        
        self.assertTrue(os.path.exists(saved_path))
        with open(saved_path, 'r', encoding='utf-8') as f:
            read_content = json.load(f)
        self.assertEqual(read_content, content)

    def test_directory_creation(self):
        content = "test"
        saved_path = self.storage.save_raw("nested/sub/source", "file.txt", content)
        self.assertTrue(os.path.exists(saved_path))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "nested/sub/source")))

if __name__ == '__main__':
    unittest.main()
