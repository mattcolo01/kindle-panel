"""Kindle 4 NT buttons that check off Home Tasks tasks.

Each button the Kindle may press gets one of the first open tasks drawn on
the screen; the image shows its symbol next to the task's checkbox. The
Kindle sends the names of the buttons pressed (POST /press) and the gateway
completes the tasks those buttons had in the last image it served.

Back is not here: on the Kindle it closes the dashboard. Power wakes the
Kindle and cannot be read as a key.
"""

import re
from dataclasses import dataclass

# Default order: the page keys first (the easiest to reach while holding the
# Kindle), then the 5-way controller, then the keys below the screen.
BUTTONS = (
    "right_next", "right_prev", "left_next", "left_prev",
    "up", "down", "left", "right", "select",
    "menu", "home", "keyboard",
)

# Home Tasks ids: list ids are config entry ids (ULIDs), task ids UUIDs; its
# WebSocket API takes 1-40 characters.
TASK_ID_RE = re.compile(r"^[0-9A-Za-z-]{1,40}$")


@dataclass(frozen=True)
class TaskRef:
    list_id: str
    task_id: str
    title: str  # for the log only
