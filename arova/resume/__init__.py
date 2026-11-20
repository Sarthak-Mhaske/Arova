"""
Arova — resume points for your whole desk.

A *resume point* is a small, portable, versioned record of work in flight:
the repo you were in, the branch, the files you had open, the tabs you were
reading, the shells you had rooted somewhere, the agents you had running, and
the one line of intent that says why.

Design commitments (these are the product, not implementation details):

1. ZERO PIXELS. Structured signals only. A resume point is kilobytes.
   Nothing on your screen is ever recorded, so there is nothing to leak.
2. RESUME, NOT SEARCH. The point exists so you can get back to work in one
   step, not so you can query your past.
3. A FORMAT, NOT A SILO. ``arova.resume/v1`` is plain JSON: human readable,
   diff-able, committable, and readable over MCP by any agent.
4. NEVER EXECUTE RECORDED COMMANDS. Restoring reopens a workspace; it does
   not replay a shell. Commands are context, never instructions.
"""

__all__ = ["SCHEMA_ID", "SCHEMA_VERSION", "__version__"]

SCHEMA_ID = "arova.resume/v1"
SCHEMA_VERSION = 1
__version__ = "0.2.0"
