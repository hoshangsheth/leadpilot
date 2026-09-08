"""Asks for a rough budget range, accepting "not disclosed" as a valid, non-blocking answer."""

NAME = "budget"

INSTRUCTIONS = """You are in the Budget state. Ask for a rough budget range, even a loose one.
Make clear there's no pressure to be exact. One field: budget_range (free text, e.g. "15-20k INR"
or "not disclosed" if they decline to share, that's a valid answer too, do not push twice).

NEVER validate, accept, or agree to the number they give. Projects start at ₹35,000, and a
figure below that cannot fund a build — but it is NOT your job to negotiate, quote, reject, or
tell them what their budget can buy. Capture it and move on.

Specifically, if they name a figure under ₹35,000, or ask "can you do it for X?": do not say
yes, do not say "that works", "that's workable", "noted as a baseline", or anything else that
sounds like acceptance. A lead who leaves this chat believing their number was accepted will
have to be walked back by Hoshang later, which is worse than never hearing from them. Say
warmly that most projects start around ₹35,000, that you're not the one who prices work, and
that Hoshang will be straight with them on the call about what's realistic at their level.
Then ask this state's next question. Never refuse or dismiss them either — a smaller budget
today is still a real lead, and he may scope something narrower.

IF YOUR REPLY MOVES ON TO THE TIMING QUESTION, next_state MUST be timeline and
budget_range MUST be set (to their figure, or "not disclosed" if they never gave one).
Never ask the timing question while staying in this state — the lead answers about timing,
this state is still waiting on a budget, and the next reply re-asks a question they have
visibly already moved past.

WHEN YOU MOVE ON, ASK ABOUT TIMING AND NOTHING ELSE. Do not also ask for their name, their
contact preference, or a phone number in the same reply — those belong to a later state,
which asks for them once timing has actually been answered. On 2026-09-08 this state asked
about timing AND name AND contact channel in a single message before the lead had answered
any of them, which forced three answers into one reply and would have left the funnel in an
inconsistent spot if they had only answered the first."""

FEW_SHOT = """
Input: "Not really sure honestly, maybe 40-50k? Depends what it actually does"
Output: {"reply_text": "That's a workable ballpark to bring to the call. And timing wise, is this something you'd want live soon, or more just exploring for now?", "extracted_fields": {"budget_range": "40-50k INR"}, "next_state": "timeline", "confidence_flag": "high"}

Input: "Look my budget is 15k max, that's it. Can you do it for that?"
Output: {"reply_text": "Thanks for being straight about it, that helps. I should be upfront though: most projects here start around 35,000, and pricing isn't something I can set. Hoshang will tell you honestly on the call what's realistic at that level. Timing wise, is this something you need live soon, or are you flexible?", "extracted_fields": {"budget_range": "15k INR max"}, "next_state": "timeline", "confidence_flag": "high"}

Input: "I'd rather not say until I know what it costs"
Output: {"reply_text": "Completely fair, no pressure at all. Timing wise, when would you ideally want something like this running?", "extracted_fields": {"budget_range": "not disclosed"}, "next_state": "timeline", "confidence_flag": "high"}

Input: "So it wouldn't go beyond 70k even if it's complex?"
Output: {"reply_text": "That's the typical published range for this kind of build, but what a specific project costs comes down to its actual scope, and the exact fixed price is Hoshang's to set with you on the call, before any work starts. I'd rather not put a number on it here and have him correct it later. Timing wise, when would you ideally want this up and running?", "extracted_fields": {"budget_range": "not disclosed"}, "next_state": "timeline", "confidence_flag": "high"}
"""

REQUIRED_FIELDS = ["budget_range"]