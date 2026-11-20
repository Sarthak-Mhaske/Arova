"""Allow ``python -m deskmark`` — useful before the console script is installed."""
from deskmark.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
