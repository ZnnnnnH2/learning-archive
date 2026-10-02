#!/usr/bin/env python3
"""Deprecated compatibility entrypoint.

The advanced GUI previously referenced an unfinished planner API surface. The
supported hierarchical GUI is API-only now, so this module delegates to it.
"""

from gui_mission_control_local import main


if __name__ == "__main__":
    main()
