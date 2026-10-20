"""Project settings. The only place where settings are defined."""

import os
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

# The model that scores free-text answers in the evaluation. The same
# provider as the main model, so the evaluation stays on the free tier.
JUDGE_PROVIDER = "gemini"
JUDGE_MODEL = "gemini-3.5-flash-lite"

# A second Gemini key, of a project with billing, for evaluation and
# development runs only, and only when a run is started with --paid: the
# free daily quota is used up first. The page, the chat sessions and the
# agents never read it; the system runs end to end on the free tier.
PAID_KEY_VARIABLE = "GEMINI_API_KEY_PAID"
# A run on the paid key stops after this many live model calls, whatever
# goes wrong: about 1-2 USD at the list price below.
PAID_RUN_MAX_LIVE_CALLS = 600

# List price of the main model in USD per million tokens, used only to
# estimate what a traced model call or an evaluated task would cost; the
# free tier costs nothing. None leaves the estimate out. Prices change:
# taken from https://ai.google.dev/gemini-api/docs/pricing (paid tier,
# Standard) on the date below, which reports print next to the cost.
# Check the page again before quoting a cost.
LLM_PRICE_INPUT_PER_MTOK = 0.30
LLM_PRICE_OUTPUT_PER_MTOK = 2.50
LLM_PRICE_DATE = "2026-10-14"

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

# --- Tracing ------------------------------------------------------------

# Where the spans of a run are sent: "off", "phoenix" (the local
# container, start it with `task up -- phoenix`) or "langfuse" (Langfuse
# Cloud; needs LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY). Personal data
# is masked for every target; a hosted target gets only an allowlist of
# attributes, no texts. Off unless the environment variable TRACING_TARGET
# says otherwise: the deployed page sets it among its secrets, so local runs
# and the evaluation stay off.
TRACING_TARGET = os.environ.get("TRACING_TARGET", "off")
# "phoenix" is the service name inside the Compose network.
TRACING_PHOENIX_ENDPOINT = "http://phoenix:6006/v1/traces"
TRACING_LANGFUSE_ENDPOINT = "https://cloud.langfuse.com/api/public/otel/v1/traces"

# --- Demo page ----------------------------------------------------------

# A chat session nobody has used for this long is closed, and with it its
# order server process: a visitor who closes the tab leaves one behind.
SESSION_IDLE_MINUTES = 15
# At most this many chat sessions are open at once. Each customer session
# runs an order server process of about 74 MB; the platform's documented
# limit is 2.7 GB and the page itself took about 1.4 GB in the deploy trial,
# so 10 sessions (about 0.75 GB) still leave some room.
MAX_OPEN_SESSIONS = 10
# A message longer than this is refused before it reaches the model. The
# longest question of the evaluation sets has 169 characters.
MAX_MESSAGE_CHARS = 1000
# Questions all visitors together may ask in one hour. The free tier allows
# about 500 model requests a day and a question takes 3 to 5; the rest is
# left for the evaluation.
MAX_QUESTIONS_PER_HOUR = 60
