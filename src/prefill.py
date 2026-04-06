"""Shared WhatsApp prefilled message shape (no Worker/pyodide deps)."""


def build_prefilled_text(
    greeting: str, context_text: str, request_text: str, ref_id: str
) -> str:
    g, c, r = greeting.strip(), context_text.strip(), request_text.strip()
    return f"{g} {c}, {r} #RefID:{ref_id}"
