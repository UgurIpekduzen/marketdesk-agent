"""Every English string shown to the end user.

The same names as in messages, which holds the Turkish ones; the strings
that only the model reads (messages.MODEL_ONLY) have no English version.
"""

# How a policy section is cited in an answer. The documents are Turkish;
# an English answer cites them under these fixed English titles.
POLICY_CITATION = "{document}, Section {number}"
POLICY_DOCUMENT_TITLES = {
    "İptal Politikası": "Cancellation Policy",
    "Hasarlı veya Yanlış Ürün Politikası": "Damaged or Wrong Item Policy",
    "Ödeme ve Geri Ödeme Politikası": "Payment and Refund Policy",
    "İade Politikası": "Returns Policy",
    "Kargo ve Gecikme Politikası": "Shipping and Delays Policy",
}

# --- Support agent ------------------------------------------------------

STEP_LIMIT_REACHED = (
    "I could not finish your request in this step. You can write your "
    "question more clearly or ask for the case to be handed to a support "
    "representative."
)
EMPTY_REPLY = "I could not write an answer just now. Please write your question again."

RETURN_REASON_LABELS = {
    "changed_mind": "changed my mind",
    "late": "late delivery",
    "damaged": "damaged item",
    "wrong_item": "wrong item",
}
REQUEST_STATUS_LABELS = {
    "PENDING_REVIEW": "waiting for review",
    "PENDING_SENIOR": "waiting for senior approval",
    "APPROVED": "approved",
    "REJECTED": "rejected",
}
# A money amount, already written the reader's way, with its currency.
MONEY = "{amount} BRL"
APPROVAL_SUMMARY = (
    "Return request to be created:\n"
    "  Order: {order}\n"
    "  Reason: {reason}\n"
    "  Refund amount: {amount}\n"
    "  The request will open as: {status}"
)
APPROVAL_QUESTION = "Do you approve? [y/n] "
RETURN_REQUEST_CREATED_DETAIL = (
    "Your return request has been created. Request number: {request_id}, "
    "status: {status}. A support representative will review it."
)
RETURN_REQUEST_NOT_CREATED = "The return request was not created: {reason}"
NOTHING_PENDING = "There is no return request waiting for approval."
APPROVAL_DECLINED = "You did not approve; no return request was created."

# --- Chat command -------------------------------------------------------

CHAT_BANNER = "MarketDesk customer support. Type 'exit' to leave.\nWrite your question:"
CHAT_PROMPT = "> "
CHAT_GOODBYE = "Goodbye."
CHAT_UNKNOWN_CUSTOMER = "No orders were found for this customer."

# --- Ops data agent -----------------------------------------------------

SQL_GAVE_UP = (
    "I could not answer this question: the queries I tried did not run and "
    "the allowed number of corrections was used up."
)
OPS_USED_SQL_HEADING = "SQL used:"
OPS_TRIED_SQL_HEADING = "SQL tried:"
OPS_CAVEAT_HEADING = "Note:"
CHAT_BANNER_OPS = (
    "MarketDesk operations data. Type 'exit' to leave.\nWrite your question:"
)

# --- Router -------------------------------------------------------------

ROUTER_OPS_NOT_ALLOWED = (
    "This information cannot be viewed from a customer account. I can help "
    "with your own orders, returns, shipping, payments and the policies."
)
ROUTER_SUPPORT_NOT_ALLOWED = (
    "Customer support actions cannot be taken in an operations session. I "
    "can answer your questions about operations data."
)
ROUTER_OUT_OF_SCOPE_CUSTOMER = (
    "I cannot help with this. I can answer your questions about your orders, "
    "returns, shipping, payments and the policies."
)
ROUTER_OUT_OF_SCOPE_OPS = (
    "I cannot help with this. I can only answer questions about operations data."
)

# --- User interface -----------------------------------------------------

UI_TITLE = "MarketDesk"
UI_CAPTION_CUSTOMER = "Customer support: orders, returns and policies"
UI_CAPTION_OPS = "Operations data: metrics and queries"
UI_SESSION_HEADING = "Session"
UI_SESSION_CUSTOMER = "Customer"
UI_SESSION_OPS = "Operations"
UI_CUSTOMER_PICKER = "Choose a situation"
# The choice screen shown before a conversation starts. No sign-in: the
# visitor picks a role and, as a customer, a demo customer's situation.
UI_CHOICE_HEADING = "How would you like to try it?"
UI_CHOICE_NOTE = (
    "No sign-in and no personal data is collected. The example customers and "
    "the demo data are shared by all visitors."
)
UI_CHOICE_CUSTOMER = "As a customer"
UI_CHOICE_CUSTOMER_TEXT = "Ask about your orders, your return rights and the policies."
UI_CHOICE_OPS = "As the operations team"
UI_CHOICE_OPS_TEXT = (
    "Answers metric questions with numbers and shows the SQL it used. The "
    "data is read only."
)
UI_START_CUSTOMER = "Start as a customer"
UI_START_OPS = "Start as operations"
UI_CHOICE_REP = "As a support representative"
UI_CHOICE_REP_TEXT = (
    "Review the return requests and support tickets the customer assistant "
    "opened; you make the decision."
)
UI_START_REP = "Start as a representative"
UI_SESSION_REP = "Support representative"
UI_REFRESH = "Refresh"
UI_CHANGE = "Change"
UI_EXAMPLES_HEADING = "Example questions"
UI_NEW_CONVERSATION = "New chat"
UI_INPUT_CUSTOMER = "Write your question"
UI_INPUT_OPS = "Write a metric question"
UI_INPUT_WAITING_APPROVAL = "First approve or cancel the request below"
UI_THINKING = "Preparing an answer..."
UI_IMAGE_REMOVED = "[image removed]"
UI_DEVELOPER_DETAILS = "Developer details"
UI_STEPS_LATEST = "Steps of the latest answer"
UI_STEPS_AGENT = "Answered by"
UI_STEPS_TOOLS = "Tools called"
UI_STEPS_NO_TOOLS = "none"
UI_STEPS_COUNTS = "{steps} steps, {tokens} tokens"
UI_AGENT_SUPPORT = "Support agent"
UI_AGENT_OPS = "Ops data agent"
UI_AGENT_ROUTER = "Router (the request was not answered in this session)"
UI_RESULT_TABLE = "Result"
# Column headers of a result table, for the dimensions of the semantic
# layer and the columns every metric result has; any other column (from
# free SQL) keeps its own name.
UI_TABLE_DIMENSIONS = {
    "purchase_month": "Month",
    "customer_state": "Customer state",
    "seller_state": "Seller state",
    "seller_key": "Seller",
    "product_category_en": "Category",
}
UI_COLUMN_NUMERATOR = "Numerator"
UI_COLUMN_DENOMINATOR = "Denominator"
UI_COLUMN_VALUE = "Value"
# Under a result written as text, when rows were left out.
TABLE_ROWS_LEFT_OUT = "... and {count} more rows"
UI_SOURCES = "Source"

# The seller report on the operations page.
UI_SELLER_REPORT = "Seller report"
UI_SELLER_REPORT_SHOW = "Build the report"
UI_SELLER_REPORT_INTRO = (
    "Sellers who hand parcels to the carrier late, highest rate first. Sellers with "
    "at least {items} items are ranked; the first {rows} are shown. Sellers are "
    "shown by a pseudonym; the real seller id appears nowhere."
)
UI_SELLER_REPORT_EMPTY = "No seller reaches the threshold under these conditions."
UI_SELLER_REPORT_SOURCES = "Where each number comes from"
SELLER_REPORT_COLUMNS = {
    "seller": "Seller",
    "items": "Items",
    "late_rate": "Late shipping rate (%)",
    "orders": "Orders",
    "gmv": "GMV (BRL)",
    "avg_review_score": "Avg. review score",
}
UI_APPROVAL_HEADING = "Your approval is needed"
UI_APPROVAL_ORDER = "Order"
UI_APPROVAL_REASON = "Reason"
UI_APPROVAL_AMOUNT = "Refund amount"
UI_APPROVAL_LEVEL = "The request will open as"
UI_APPROVE = "Approve"
UI_DECLINE = "Cancel"
UI_PREPARING_DATABASE = (
    "Preparing the demo data: the dataset is downloaded and the database is "
    "built. This happens only when the app first starts and may take a "
    "minute or two."
)
UI_PAUSED = "The page is down for maintenance. Please try again a little later."
UI_NO_DATABASE = (
    "The demo data could not be prepared. Please refresh the page in a few "
    "minutes; locally the database is built with `task data`."
)
# A credit line in the usual English form, like the dataset's name and
# licence.
UI_DATA_NOTE = "Data: Olist Brazilian E-Commerce, CC BY-NC-SA 4.0"
# The language switch: its label is the same in both languages, so either
# reader finds it.
UI_LANGUAGE_SWITCH = "Dil · Language"
UI_LANGUAGE_HELP = "Changing the language starts a new conversation."
UI_LANGUAGE_CHANGED = (
    "A new conversation started because the language changed. A request that "
    "was waiting for approval in the earlier one was not created."
)
UI_SESSION_EXPIRED = (
    "The earlier chat was closed after a long time without activity; a new "
    "chat has started."
)
UI_ERROR_FULL = (
    "The demo is serving many visitors right now. Please try again in a few "
    'minutes with the "New chat" button.'
)
UI_ERROR_TOO_LONG = "Your message is too long; please write at most {limit} characters."
UI_ERROR_QUESTION_LIMIT = (
    "The demo is very busy right now: the question limit for this hour has "
    "been reached. Please try again a little later."
)
UI_ERROR_DAILY_BUDGET = (
    "The demo has used up today's questions. Please try again tomorrow."
)
UI_NO_CUSTOMERS = "No example customers were found in the database."
UI_ERROR_QUOTA = (
    "The AI service's free usage quota seems to be used up right now. Please "
    "try again after a while."
)
UI_ERROR_BUSY = (
    "The AI service is busy or not answering right now. Please try again a "
    "little later."
)
UI_ERROR_TIMEOUT = "The answer did not arrive in time. Please try again."
UI_ERROR_NOT_CONFIGURED = (
    "The app is not configured yet: the AI service's key is not set."
)
UI_ERROR_KEY_REFUSED = (
    "The AI service did not accept the app's key; the key has to be renewed. "
    "Please try again later."
)
UI_ERROR_GENERIC = (
    "Something unexpected went wrong and your request was not answered. "
    "Please try again."
)
DEMO_CUSTOMER_LABELS = {
    "recent_delivery": "Customer with a recently delivered order",
    "late_delivery": "Customer with a late delivered order",
    "in_transit": "Customer with an order on its way",
    "window_passed": "Customer whose return period has passed",
    "many_orders": "Customer with many orders",
}

# Example questions offered above an empty conversation, the English
# versions of the Turkish ones; none is from the held-out test split.
# Customer questions that need the situation of the demo customer:
EXAMPLE_QUESTIONS_BY_SITUATION = {
    "recent_delivery": [
        "I changed my mind about my last order and want to return it.",
        "My last order arrived damaged, can you open a return request?",
    ],
    "late_delivery": ["How many days late was my last order?"],
    "in_transit": ["Where is my last order and when will it arrive?"],
    "window_passed": [
        "I want to return my last order, I changed my mind.",
        "My last order turned out to be damaged, can I still return it?",
    ],
    "many_orders": [
        "Can you list my orders?",
        "What is the status of the order I placed most recently?",
    ],
}
# Customer questions that fit every situation.
EXAMPLE_QUESTIONS_GENERAL = [
    "Where is my last order?",
    "I need help with my order.",
]
# Customer questions answered from the policies.
EXAMPLE_QUESTIONS_POLICY = [
    "If my order cannot be supplied, how is my money refunded?",
    "Can I cancel an order that has already been shipped?",
    "I missed my return period, can I still claim my shipping fee for a late delivery?",
    "How do I open a return request for a damaged item, and who approves it?",
    "I paid part of my order with a voucher; if I return it, how is my money refunded?",
    "How do I cancel an order that has not been shipped yet?",
    "How many days does it take for a refund to reach my account?",
]
EXAMPLE_QUESTIONS_OPS = [
    "Which are the 5 product categories with the highest GMV?",
    "What is the average review score by month in 2018?",
    "Among customer states with at least 300 orders, which 5 have the highest cancellation rate?",
    "What is the number of orders by month in 2018?",
    "What was the late delivery rate in the state of SP in July 2018?",
    "Among categories with at least 100 orders, which 5 have the highest late delivery rate?",
    "What is the GMV of August 2018?",
    "Among states with at least 500 orders, which 3 have the highest cancellation rate?",
    "In how many different orders was each payment type used?",
    "What are the order counts by month in 2018 in the states of SP and RJ?",
]

# The support rep's review queue. Decisions on return requests and closing
# tickets are made in code; these are the answers to a refused one.
REVIEW_NOT_FOUND = "No record was found with this number."
REVIEW_SENIOR_ONLY = (
    "This request is above 500 BRL: it needs senior approval and cannot be "
    "approved or rejected from this screen."
)
REVIEW_ALREADY_DECIDED = "This request has already been decided."
REVIEW_TICKET_ALREADY_CLOSED = "This ticket has already been closed."
REVIEW_INVALID_DECISION = "Invalid decision."

# The support rep's console.
UI_REVIEW_HEADING = "Review queue"
UI_REVIEW_NOTE = (
    "You make the decisions; the AI makes no decision on this screen. The "
    "ticket summaries were written by the AI: check the decision against the "
    "request's own details."
)
UI_REVIEW_REQUESTS_TAB = "Return requests ({count})"
UI_REVIEW_TICKETS_TAB = "Support tickets ({count})"
UI_REVIEW_NO_REQUESTS = "No return requests are waiting."
UI_REVIEW_NO_TICKETS = "No support tickets are open."
UI_REVIEW_DECIDED = "Decided (last {count})"
UI_REVIEW_APPROVE = "Approve"
UI_REVIEW_REJECT = "Reject"
UI_REVIEW_CLOSE = "Close"
UI_REVIEW_SENIOR_NOTE = (
    "Above 500 BRL: it needs senior approval and cannot be decided from this screen."
)
UI_REVIEW_REQUEST_TITLE = "Request {id} · Order `{order}` · Customer `{customer}`"
UI_REVIEW_REQUEST_DETAILS = "{reason} · {amount} · {date} · {status}"
UI_REVIEW_TICKET_TITLE = (
    "{number} · {priority} priority · {date} · Customer `{customer}`"
)
UI_REVIEW_DECIDED_DONE = "Request {id}: {status}."
UI_REVIEW_TICKET_CLOSED = "{number} closed."
PRIORITY_LABELS = {"low": "low", "normal": "normal", "high": "high"}

# "How it was computed": a line under a metric answer, written by code from
# the metric call, not by the model.
COMPUTED_HEADING = "How it was computed"
COMPUTED_GROUP_BY = "grouped by: {dimensions}"
COMPUTED_FILTER = "filter: {filters}"
COMPUTED_PERIOD_BOTH = "order date {start} – {end}"
COMPUTED_PERIOD_FROM = "order date {start} and later"
COMPUTED_PERIOD_TO = "order date {end} and earlier"
COMPUTED_MIN_COUNT = "at least {count} {unit}"
COMPUTED_UNITS = {"order": "orders", "item": "items"}
COMPUTED_ORDER = {
    "value_desc": "by value, descending",
    "value_asc": "by value, ascending",
}
COMPUTED_TOP = "top {top}"
COMPUTED_REPORT_SELLERS = "for the sellers of the report only"
COMPUTED_SCOPE = "orders placed on or before {today}"

# The SQL of the newest answer, opened from the sidebar in a wide window.
UI_SHOW_SQL = "Show the SQL"
UI_SQL_DIALOG_TITLE = "SQL query"
