"""Entry point used by the PyInstaller build (the package's own __main__ uses relative imports)."""
import sys

from datawatch.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
