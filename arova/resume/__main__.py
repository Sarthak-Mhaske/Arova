"""Allow ``python -m arova.resume`` — useful before the console script is installed."""
from arova.resume.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
