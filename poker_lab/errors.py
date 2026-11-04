"""Stable error codes for clients; English messages are a fallback for logs."""

ERRORS = {
    "expired": (401, "Session or table expired. Please reconnect."),
    "not_found": (404, "Not found."),
    "hand_not_found": (404, "Hand is unfinished or no longer available."),
    "invite_not_found": (404, "Invite not found or expired."),
    "table_full": (409, "This table is full."),
    "bad_name": (400, "Name must contain 1-12 characters and no control characters."),
    "bad_request": (400, "Invalid request."),
    "stale": (409, "The decision has changed. Please try again."),
    "not_your_turn": (409, "It is not your turn or the hand is over."),
    "illegal_action": (409, "That action or amount is not allowed."),
    "hand_in_progress": (409, "The current hand has not finished."),
    "not_seated": (409, "This seat is not controlled by an active participant."),
    "forbidden_origin": (403, "Requests must come from this site."),
    "server_error": (500, "Unexpected server error."),
}


class GameError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(ERRORS[code][1])


def error_response(code):
    status, message = ERRORS[code]
    return status, {"code": code, "error": message}
