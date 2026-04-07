"""Shared WhatsApp prefilled message shape (no Worker/pyodide deps)."""

GREETINGS = [
    "Hey!",
    "Hi there!",
    "Hello!",
    "Hi!",
    "Hey there!",
    "Greetings!",
    "Hello there!",
]

# {topic} is replaced by the context_text argument at generation time
CONTEXT_TEMPLATES = [
    "I came across {topic}",
    "I saw {topic}",
    "I noticed {topic}",
    "I found {topic}",
    "I just saw {topic}",
    "I'm interested in {topic}",
    "Regarding {topic}",
]

REQUEST_VARIANTS = [
    "I would like more information",
    "I'd love to know more",
    "could you share details?",
    "please send me more info",
    "can I get more details?",
    "I'd like to learn more",
    "please tell me more",
]

_G = len(GREETINGS)
_C = len(CONTEXT_TEMPLATES)
_R = len(REQUEST_VARIANTS)


def pick_variants(qr_id: int) -> tuple[str, str, str]:
    """Return (greeting, context_template, request) deterministically from qr_id.

    Uses mixed-radix selection so each dimension cycles independently:
      greeting  changes every 1 id
      context   changes every G ids
      request   changes every G*C ids
    Total unique combinations: G * C * R (343 with 7×7×7 defaults).
    """
    g = GREETINGS[qr_id % _G]
    c = CONTEXT_TEMPLATES[(qr_id // _G) % _C]
    r = REQUEST_VARIANTS[(qr_id // (_G * _C)) % _R]
    return g, c, r


def build_prefilled_text(
    greeting: str,
    context_text: str,
    request_text: str,
    ref_id: str,
    qr_id: int = 0,
) -> str:
    """Build the WhatsApp prefilled message for a QR code.

    When qr_id > 0 the greeting and request are derived from the variation
    lists (unique per QR), and context_text is used as the topic injected into
    the selected context template.  When qr_id == 0 the legacy single-template
    behaviour is preserved.
    """
    if qr_id > 0:
        g, c_tpl, r = pick_variants(qr_id)
        topic = context_text.strip()
        c = c_tpl.format(topic=topic)
    else:
        g = greeting.strip()
        c = context_text.strip()
        r = request_text.strip()

    return f"{g} {c}, {r} #RefID:{ref_id}"
