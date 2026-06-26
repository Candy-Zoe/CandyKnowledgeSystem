import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from core.database import DatabaseManager


def main():
    db = DatabaseManager(str(config.DB_PATH))
    output = str(config.DATA_DIR / "knowledge_base_export.json")
    db.export_to_json(output)
    print(f"Exported to {output}")


if __name__ == "__main__":
    main()
