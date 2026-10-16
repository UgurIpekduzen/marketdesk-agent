# Security review of the chat page

The page runs on Streamlit: the browser only sends "this was clicked" and "this was typed", and everything is decided on the server. A visitor can still write those messages by hand, so any check the page makes is a convenience; the rule has to hold on the server. This review lists what the page decides, checks each decision against messages no click could send, and records the result.

Review date: 2026-10-16. Tests named below are in `tests/`.

## Findings

| # | What the page decides or shows | Result | How it is held, and the test |
|---|---|---|---|
| F1 | The customer is chosen from a list of five demo customers | Holds | A value missing from the list is turned back into the default choice by the framework; the identity reaches the order server only from the server-side list. `test_a_customer_missing_from_the_list_is_not_taken` |
| F1 | Error details after an unexpected failure | Fixed | The framework's default showed the traceback in the browser. `.streamlit/config.toml` sets `showErrorDetails = "none"`. `test_the_page_shows_no_error_details_and_keeps_its_protections` |
| F2 | Markdown in the model's answer | Fixed | An image in markdown makes the browser fetch its address at once, so a model talked into writing one could send data to any site. Images are replaced with a note and every other start of an image is escaped (`src/ui/view.py`). `test_a_markdown_image_in_an_answer_is_not_drawn`, `test_no_form_of_markdown_image_is_left_to_draw`, `test_an_image_in_the_model_answer_reaches_no_other_site` |
| F2 | Tool names in the steps panel | Fixed | Drawn as inline code, which is not read as markdown. `test_tool_names_are_drawn_as_code_that_cannot_become_markdown` |
| F3 | Length of a message | Fixed | No limit before. The chat session refuses a message over 1,000 characters before it reaches the model; the chat box limits it too, for the visitor only. `test_a_message_over_the_limit_never_reaches_the_model`, `test_a_long_message_sent_past_the_box_is_refused_on_the_server` |
| F4 | How many questions are asked | Fixed | No limit before: one visitor with many tabs could use up the free quota. A limit of 60 questions an hour is shared by all visitors. `tests/test_question_limit.py`, `test_sessions_share_the_question_limit_and_approvals_do_not_count`, `test_the_hourly_question_limit_is_said_plainly` |
| F5 | The chat box is closed while a return request waits for approval | Holds | A message sent through it is answered, and what is approved stays the request the card shows: the server holds the pending request and the card is drawn from it. `test_a_message_through_the_closed_chat_box_leaves_the_approval_as_shown` |
| F6 | Demo customers are shared between visitors | Accepted | A request one visitor opens is seen by the next one who picks the same customer. The data is a public dataset with no personal data; the sidebar says the demo data is shared. |
| F7 | Every visitor may open an operations session | Accepted | The demo has no sign-in. Operations sessions read only the safe views, on a read-only connection; a real deployment would take the session type from a login. |
| F8 | The session type is chosen with a radio button | Holds | An unknown value falls back to the customer session. `test_an_unknown_session_type_falls_back_to_the_customer_session` |
| F9 | XSRF and CORS protection | Holds | The framework's defaults, written down in `.streamlit/config.toml` and checked by a test. |
| F10 | Approve and decline appear only with the card | Holds | A click sent for a button that is no longer on the page is ignored, and the order server answers `NOTHING_PENDING` to an approval with nothing pending. `test_a_click_on_an_approve_button_that_is_gone_writes_nothing` |
| F11 | The steps panel and the SQL panel show tool names, token counts and SQL | Accepted | Shown on purpose; nothing secret is in them. |

## Automated review

Claude Code's `/security-review` read the whole branch twice (2026-10-16). It found no vulnerability rated 8 of 10 or higher. Below that bar it noted that the first image pattern missed images with nested brackets and shortcut references (closed by escaping every start of an image) and that tool names in the steps panel were drawn as markdown (closed by drawing them as code).

## Still open

- One visitor can still hold all ten chat sessions or the hourly limit for a while; the page cannot tell visitors apart reliably. Accepted for a demo.
- The review reads code and sends crafted messages through tests; it is not a penetration test of the deployed page.
