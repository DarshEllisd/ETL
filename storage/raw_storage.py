import os
import json
from typing import Union, Dict, Any

class RawStorage:
    def __init__(self, base_dir: str = None):
        """
        Initialize RawStorage.
        :param base_dir: Base directory for storing raw files. Defaults to project root 'raw'.
        """
        if base_dir is None:
            # Default to a 'raw' directory in the parent folder of 'storage' (i.e. the project root)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.join(os.path.dirname(current_dir), 'raw')
        
        self.base_dir = os.path.abspath(base_dir)

    def save_raw(self, source: str, filename: str, content: Union[str, Dict[str, Any]]) -> str:
        """
        Saves raw data from a connector to storage.
        :param source: The source name (e.g., 'gmail', 'whatsapp').
        :param filename: Target filename for storage.
        :param content: String content or a JSON-serializable dictionary.
        :returns: Absolute path to the saved file.
        """
        target_dir = os.path.join(self.base_dir, source)
        os.makedirs(target_dir, exist_ok=True)
        
        target_path = os.path.join(target_dir, filename)
        
        try:
            if isinstance(content, dict):
                with open(target_path, 'w', encoding='utf-8') as f:
                    json.dump(content, f, indent=2, ensure_ascii=False)
            else:
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            return target_path
        except IOError as e:
            raise IOError(f"Failed to write raw data for source '{source}' to {target_path}: {e}")
