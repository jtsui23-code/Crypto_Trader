import json
from pathlib import Path

def get_whales():
    base_path = Path(__file__).parent.parent
    file_path = base_path / "data" / "whales.json"

    try:
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        else:
            print(f"Warning: {file_path} not found.")
            return []
    except Exception as e:
        print(f"Error reading whales.json: {e}")
        return []
    
print(get_whales())