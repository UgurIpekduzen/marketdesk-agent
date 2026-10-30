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

# The automated red team scan (eval/red_team.py): the model that writes the
# attacks and the one that judges the answers. Another provider than the
# system's, so the scan does not use the Gemini quota the system needs. Two
# models: gpt-oss-120b refused to write attack variants (0 of 12 in a trial
# on 2026-10-20, also when told the test is authorised), Qwen wrote 6 of 6;
# a judge other than the attacker does not score its own work, and Groq's
# daily token limit is counted per model.
REDTEAM_PROVIDER = "groq"
REDTEAM_ATTACKER_MODEL = "qwen/qwen3.8-27b"
REDTEAM_JUDGE_MODEL = "openai/gpt-oss-120b"
# A scan stops after this many live calls to the system's own model.
REDTEAM_MAX_LIVE_CALLS = 150
# The attacker of the multi-turn scan writes with some variety. At 0, and
# with its answers cached, an attack it once refused to write is refused
# again on every run (2 of 6 conversations on 2026-10-22).
REDTEAM_MULTI_TURN_ATTACKER_TEMPERATURE = 0.7
# The most the attacker may write in one answer. Without it Groq counts 1,200
# output tokens for a request, over Qwen's 1,000 a minute, and refuses the
# request before the model sees it (8 refusals in one scan on 2026-10-27).
REDTEAM_ATTACKER_MAX_TOKENS = 800
# The judge for sets about what the system's own model gets wrong, such as
# misinformation, when a run asks for it: a model of another provider, so
# the system's model does not grade its own answers. The scan's judge.
INDEPENDENT_JUDGE_PROVIDER = REDTEAM_PROVIDER
INDEPENDENT_JUDGE_MODEL = REDTEAM_JUDGE_MODEL
# How much the independent judge thinks before it answers. At the default,
# gpt-oss-120b spent so much of its output on thinking that a list of the
# facts in the whole policy text was cut off before its end (2026-10-21).
INDEPENDENT_JUDGE_REASONING_EFFORT = "low"

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

# What one free SQL query may build, whatever the function it calls. The
# timeout counts steps of the engine and one function call is one step, so
# `format('%.*c', 900000000, 'x')` made 900 MB in a fraction of a second.
# The longest value (text or blob) the engine may build:
SQL_MAX_VALUE_BYTES = 100_000
# The most characters of text and blobs all the rows of one answer may hold:
SQL_MAX_RESULT_BYTES = 2_000_000
# A backstop for the memory of the engine in this process (SQLite holds one
# limit for all its connections). Far above what the data needs.
SQL_HEAP_LIMIT_BYTES = 512 * 1024 * 1024

# After a free SQL query fails, the agent may correct it this many times
# within one question. Then it has to say that it could not answer.
SQL_MAX_CORRECTIONS = 2

# The seller report ranks sellers by their late-shipping rate. A seller with
# fewer items than this is left out: of 3,095 sellers 634 reach 30 items,
# and they hold 83% of the orders (measured on the full data, 2026-10-22).
SELLER_REPORT_MIN_ITEMS = 30
SELLER_REPORT_ROWS = 20

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

# --- Review Insight Agent ----------------------------------------------

# The most review texts one call of summarize_reviews hands to the model, and
# the longest text kept of one review (longer ones are cut). The agent works
# on a sample: the call says how many reviews matched the filters.
REVIEW_MAX = 50
REVIEW_MAX_CHARS = 600

# --- Critic -------------------------------------------------------------

# The operations agent's answer is checked in code before it is shown: every
# number in it must be one a tool returned. If not, the model is asked once
# more to answer with the tools' numbers only; an answer that still holds
# others is shown with a note. The evaluation switches it off with
# --no-critic, to measure what it does.
CRITIC_ENABLED = True
CRITIC_MAX_CORRECTIONS = 1
# How the model is asked to correct: "plain" asks for the tools' numbers only;
# "compute" also says to compute a derived value (a sum, a difference, a
# share, a mean) with run_sql. "compute" is in use (user, 2026-10-23): on the
# number traps it answered the question where "plain" left the figure out.
# The evaluation measures both (--critic-variant); the results of the other
# one have a file name of their own.
CRITIC_DEFAULT_VARIANT = "compute"
CRITIC_CORRECTION_VARIANT = CRITIC_DEFAULT_VARIANT

# --- Agent loop ---------------------------------------------------------

# Upper limit on the steps an agent may take for one user message. It counts
# model calls, and LlamaIndex raises when it handles the output of the last
# one allowed, even if that output is the answer: a message that needs seven
# tool calls and an answer on the eighth call gets the step-limit message.
# No evaluation example reached it (checked on 2026-10-31 in the results
# files). tests/test_support_agent.py keeps the behaviour.
MAX_STEPS = 8
# Upper limit on the tool calls of one user message, over all its steps: a
# model may ask for many calls in one step. Measured on 2026-10-21, no
# example of the golden, attack or multi-turn sets used more than 4; with 12
# a message runs at most 12 queries of SQL_TIMEOUT_SECONDS each.
MAX_TOOL_CALLS_PER_MESSAGE = 12

# --- Tracing ------------------------------------------------------------

# Where the spans of a run are sent: "off", "phoenix" (the local
# container, start it with `task up -- phoenix`) or "langfuse" (Langfuse
# Cloud; needs LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY). Personal data
# is masked for every target; a hosted target gets only an allowlist of
# attributes, no texts. Off unless the environment variable TRACING_TARGET
# says otherwise: the deployed page sets it among its secrets, so local runs
# and the evaluation stay off.
TRACING_TARGET = os.environ.get("TRACING_TARGET", "off")

# Stops the page at once: set to 1 among the deploy platform's secrets (or in
# the environment), and every page run shows a notice and nothing else, so
# no model is called and no session takes a message. Read at every page run.
PAUSE_VARIABLE = "MARKETDESK_PAUSED"
# "phoenix" is the service name inside the Compose network.
TRACING_PHOENIX_ENDPOINT = "http://phoenix:6006/v1/traces"


def langfuse_endpoint(base_url: str) -> str:
    """Where Langfuse Cloud takes spans, for the region its keys belong to.

    Only https: the keys go in a header, and a typo must not send them in the
    clear.
    """
    if not base_url.lower().startswith("https://"):
        raise ValueError("LANGFUSE_BASE_URL must start with https://")
    return base_url.rstrip("/") + "/api/public/otel/v1/traces"


# Langfuse keys belong to one region: the EU one (the default) or
# https://us.cloud.langfuse.com. Keys of one are refused by the other.
LANGFUSE_BASE_URL = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
# How many of the newest observations the error tracing page reads by default
# (a local page, `task trace:dashboard`; it reads the traces with the keys of
# the project).
TRACING_DASHBOARD_OBSERVATIONS = 1000

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
# Model calls all visitors together may make in the last 24 hours. A question
# can take up to MAX_STEPS + 1 calls (the router and every step), so the
# hourly question limit alone would let one visitor use the free tier's 500
# requests a day within an hour (measured 2026-10-21). Counted at each call;
# 100 are left for the evaluation.
MAX_MODEL_CALLS_PER_DAY = 400
