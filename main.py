"""Repository entry point: run with ``python main.py`` from any directory."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from durga_lineart.main import main

if __name__ == "__main__":
    main()
