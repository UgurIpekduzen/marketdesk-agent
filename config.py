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
# The fallback is a second provider kept ready for a day the main one is
# down. Nothing is sent to it unless LLM_USE_FALLBACK is switched on here.
LLM_FALLBACK_PROVIDER = "groq"
LLM_FALLBACK_MODEL = "qwen/qwen3.8-27b"
LLM_USE_FALLBACK = False
# 0 makes the model pick the most likely answer every time: the same
# question gives the same answer, which the evaluation needs.
LLM_TEMPERATURE = 0

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

# A free SQL query that runs longer than this many seconds is stopped.
SQL_TIMEOUT_SECONDS = 5

# After a free SQL query fails, the agent may correct it this many times
# within one question. Then it has to say that it could not answer.
SQL_MAX_CORRECTIONS = 2

# --- Embedding ----------------------------------------------------------

# multilingual-e5-small as a quantized ONNX file: the same model, small
# enough for the deploy platform's memory. The revision pins the exact
# files, so a later change in the repository cannot reach this project.
EMBEDDING_MODEL_REPO = "Xenova/multilingual-e5-small"
EMBEDDING_MODEL_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
EMBEDDING_MODEL_FILE = "onnx/model_quantized.onnx"
EMBEDDING_TOKENIZER_FILE = "tokenizer.json"
EMBEDDING_DIMENSIONS = 384
# Longer texts are cut to this many tokens, the model's limit.
EMBEDDING_MAX_TOKENS = 512

# --- Agent loop ---------------------------------------------------------

# Upper limit on the steps an agent may take for one user message.
MAX_STEPS = 8
