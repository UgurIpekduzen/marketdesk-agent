# Do the tests notice a guard that is switched off?

Each guard is broken in the running process (never in the source) and the tests meant to watch it are run. A guard whose tests still pass when it is broken is a hole in the tests.

| Guard broken | What is switched off | Unit tests | Attack sets (dev, with the model) |
|---|---|---|---|
| `control_nothing_broken` | nothing (the control: its tests must pass) | test_critic.py, test_approval.py: tests pass, as they must | not run |
| `approval_off` | the approval token is not checked: a request is written without a click | test_approval.py, test_return_requests.py: noticed (1 failed first) | not run |
| `existence_leak` | an order of another customer answers differently from a missing one | test_orders.py, test_leak.py: noticed (1 failed first) | not run |
| `validator_tables_off` | free SQL may read any table, not only the safe views | test_sql_validator.py, test_sql_runner.py: noticed (1 failed first) | not run |
| `theme_check_off` | any quote is accepted as a piece of a review | test_review_themes.py: noticed (1 failed first) | not run |
| `outbound_off` | personal data is not masked before the text leaves for the provider | test_outbound.py, test_pii.py, test_leak.py: noticed (1 failed first) | not run |
| `write_allowlist_off` | the database connections may write to any table | test_write_access.py, test_review_queue.py: noticed (1 failed first) | not run |
| `router_roles_off` | the router lets a session reach any agent | test_orchestrator.py: noticed (1 failed first) | not run |
| `critic_off` | the numbers of an answer are not checked against the tools | test_critic.py: noticed (1 failed first) | not run |
| `safe_markdown_off` | the model's links and images reach the page as they are | test_view.py: noticed (1 failed first) | not run |
| `card_binding_off` | a click writes the request that waits, not the card the person saw | test_mcp_server.py, test_chat_session.py: noticed (1 failed first) | not run |

Noticed by the unit tests: 10 of 10.
