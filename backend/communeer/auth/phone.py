"""Normalizes a user-entered phone number into the WhatsApp JID format this
codebase already uses elsewhere (`Member.wa_id`, e.g. `"4915500000000@c.us"`)
— no phone-validation library dependency, just digit-stripping and a sane
length check (E.164 allows up to 15 digits; 8 is a generous lower bound for
"this can't possibly be a real number with a country code").
"""

import re

from communeer.errors import bad_request

_MIN_DIGITS = 8
_MAX_DIGITS = 15


def normalize_phone_to_wa_id(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if not (_MIN_DIGITS <= len(digits) <= _MAX_DIGITS):
        raise bad_request("Enter a valid phone number, including country code.")
    return f"{digits}@c.us"
