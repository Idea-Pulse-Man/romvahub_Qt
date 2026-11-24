"""romva hub desktop app. Run:  python main.py   (add --minimized to start in the tray)."""

import sys

from romvahub_app.app import main

if __name__ == "__main__":
    sys.exit(main())
