import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from core.database import DatabaseManager


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_db.py <json_file>")
        return
    json_path = sys.argv[1]
    db = DatabaseManager(str(config.DB_PATH))
    db.import_from_json(json_path)
    print(f"Imported from {json_path}")


if __name__ == "__main__":
    main()
