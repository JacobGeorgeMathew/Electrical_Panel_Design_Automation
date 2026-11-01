"""Print-only handoff instructions. This script never opens a DB connection."""
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[2]
    export=root/"component_data_pipeline"/"data"/"exports"/"components.json"
    print("Review this export before importing:")
    print(export)
    print("The main project's catalog import is backend/app/persistence/import_legacy.py, invoked through backend/tools/initialize_development.py or backend/app/persistence/manage.py.")
    print("Those commands may write to PostgreSQL. This helper does not run them. Review schema mapping, create a database backup, and choose an explicitly disposable/reviewed database before importing.")

if __name__ == "__main__": main()
