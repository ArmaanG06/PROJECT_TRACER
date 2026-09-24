from pathlib import Path
import yaml

def get_project_root() -> Path:
    # walks up from this file until it finds pyproject.toml
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise FileNotFoundError("pyproject.toml not found — project root undetermined")

def load_config():
    root = get_project_root()
    with open(root / "configs.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg['data']['DB_path'] = str(root / cfg['data']['DB_path'])
    cfg['data']['constituents'] = str(root / cfg['data']['constituents']) + "/"
    return cfg
