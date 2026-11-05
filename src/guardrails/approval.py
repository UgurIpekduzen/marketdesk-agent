"""Human approval for the one write action: opening a return request.

A return request is written only with a token that proves a person said
yes. The token is made here, by code, after the person approves; it is kept
on the server side and never shown to the model. A model that says "the
customer approved" has no token, so nothing is written.

A token is random, works once, and is tied to one action: the same order,
reason and amount the person saw. Change any of them and it no longer fits.
"""

import secrets
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ReturnAction:
    """Exactly what the person is asked to approve."""

    order_id: str
    reason: str
    amount: Decimal


class Approvals:
    """The approvals of one session."""

    def __init__(self) -> None:
        # The action shown to the person and waiting for their answer.
        self._awaiting: ReturnAction | None = None
        # Tokens handed out and not used yet, each with its action.
        self._tokens: dict[str, ReturnAction] = {}

    @property
    def awaiting(self) -> ReturnAction | None:
        """The action waiting for the person's answer, if any."""
        return self._awaiting

    def request(self, action: ReturnAction) -> None:
        """Remember the action a person now has to decide on.

        Args:
            action (ReturnAction): The action the person has to decide on.
        """
        self._awaiting = action

    def approve(self) -> str:
        """Record that the person said yes and return the token for it.

        Called by the user interface only, when the person confirms. Never
        called from a tool the model can reach.
        """
        if self._awaiting is None:
            raise LookupError("no action is waiting for approval")
        token = secrets.token_urlsafe(32)
        self._tokens[token] = self._awaiting
        self._awaiting = None
        return token

    def reject(self) -> None:
        """Record that the person said no."""
        self._awaiting = None

    def consume(self, token: str | None, action: ReturnAction) -> bool:
        """Use up a token; True only if it was issued for exactly this action.

        A token is gone after one try, whether it fitted or not.

        Args:
            token (str | None): The approval token, or None.
            action (ReturnAction): The action about to be done.

        Returns:
            True only if the token was issued for exactly this action.
        """
        if token is None:
            return False
        return self._tokens.pop(token, None) == action
