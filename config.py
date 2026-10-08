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
# Short window (R6): the customer changed their mind or the order was late.
RETURN_WINDOW_SHORT_DAYS = 14
# Long window (R7): the item was damaged or wrong. Also the limit for a
# freight-only claim on a late delivery (R9).
RETURN_WINDOW_LONG_DAYS = 30

# A delivery this many days after the estimated date, or later, earns a
# freight refund (R9).
FREIGHT_REFUND_DELAY_DAYS = 10

# A refund above this amount in BRL needs senior approval (R10).
APPROVAL_THRESHOLD_BRL = 500

# --- Free SQL -----------------------------------------------------------

# The most rows a free SQL query may return. A query without a LIMIT gets
# this one; a larger LIMIT is lowered to it.
SQL_MAX_ROWS = 1000

# --- Agent loop ---------------------------------------------------------

# Upper limit on the steps an agent may take for one user message.
MAX_STEPS = 8
