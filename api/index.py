import sys
from pathlib import Path

# Add parent directory to path
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import the app.py module directly by its file path to avoid app/ package conflict
import importlib.util

spec = importlib.util.spec_from_file_location(
    "main_app",
    Path(__file__).parent.parent / "app.py"
)
if spec and spec.loader:
    main_app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main_app)
    app = main_app.app
else:
    raise RuntimeError("Failed to load app.py")