from pathlib import Path
import os
import json

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("COMPONENT_PIPELINE_DATA_DIR", ROOT / "data")).expanduser().resolve()

def load_yaml(name):
    with (ROOT / "config" / name).open(encoding="utf-8") as stream:
        text=stream.read()
    try:
        import yaml
    except ImportError:
        # JSON is a YAML 1.2 subset, so source config remains readable as YAML without PyYAML.
        return json.loads(text)
    return yaml.safe_load(text)

def source_config(source_id):
    sources = load_yaml("sources.yaml")["sources"]
    if source_id not in sources:
        raise KeyError(f"Unknown source ID {source_id!r}. Available: {', '.join(sources)}")
    return source_id, sources[source_id]
