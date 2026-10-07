"""Project settings. The only place where settings are defined."""

from datetime import date

# --- Time ---------------------------------------------------------------

# "Today" for all business logic. Never use the machine clock for it.
SIMULATED_TODAY = date(2018, 9, 1)

# --- Model --------------------------------------------------------------

# The provider is chosen here and nowhere else: no other module may know
# which provider is in use.
LLM_PROVIDER = "gemini"
LLM_MODEL = "gemini-3.5-flash-lite"

# --- Return rules -------------------------------------------------------

# Return windows in calendar days. The delivery day is day 0 and the last
# day of a window is still inside it.
RETURN_WINDOW_SHORT_DAYS = 14
RETURN_WINDOW_LONG_DAYS = 30

# Amount in BRL that separates the two approval levels.
APPROVAL_THRESHOLD_BRL = 500

# --- Agent loop ---------------------------------------------------------

# Upper limit on the steps an agent may take for one user message.
MAX_STEPS = 8
