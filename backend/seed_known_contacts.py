"""Mark numbers as human-only, so the bot never engages them.

Run this BEFORE any warm outreach. Anyone seeded here who messages the LeadPilot number is
recorded and silently handed to Hoshang, with no qualification questions asked — the same
end state as routing.detect_bypass, but guaranteed up front rather than dependent on the
contact happening to phrase their message in a way the bypass patterns recognize.

Belt-and-braces on purpose: pattern matching will never catch every warm opener, and the
cost of getting it wrong (asking a friend or a referral for their budget, by robot) is far
higher than the cost of seeding a list.

Usage, from backend/:
    venv/Scripts/python.exe seed_known_contacts.py 919820012345 919833044556
    venv/Scripts/python.exe seed_known_contacts.py --file contacts.txt   # one number per line
    venv/Scripts/python.exe seed_known_contacts.py --list                # show current
    venv/Scripts/python.exe seed_known_contacts.py --remove 919820012345

Numbers must be in WhatsApp's format: country code, no +, no spaces (919820012345).
"""

import argparse
import re
import sys

from db.db import SessionLocal
from db.models import Lead

_VALID_NUMBER = re.compile(r"^\d{10,15}$")


def _normalize(raw: str) -> str | None:
    """Strip the formatting people actually paste (+91, spaces, dashes, brackets)."""
    digits = re.sub(r"[^\d]", "", raw or "")
    if not digits:
        return None
    # A bare 10-digit Indian mobile is the most common paste; prepend the country code so it
    # matches what Meta's webhook will send.
    if len(digits) == 10:
        digits = "91" + digits
    return digits if _VALID_NUMBER.match(digits) else None


def seed(numbers: list[str]) -> None:
    db = SessionLocal()
    try:
        added, already, invalid = [], [], []
        for raw in numbers:
            number = _normalize(raw)
            if number is None:
                invalid.append(raw)
                continue
            lead = db.query(Lead).filter_by(wa_number=number).first()
            if lead is None:
                db.add(Lead(wa_number=number, human_takeover=True))
                added.append(number)
            elif lead.human_takeover:
                already.append(number)
            else:
                lead.human_takeover = True
                added.append(number)
        db.commit()

        for number in added:
            print(f"  seeded   {number}")
        for number in already:
            print(f"  already  {number}")
        for raw in invalid:
            print(f"  INVALID  {raw!r} — use country code and digits only, e.g. 919820012345")
        print(f"\n{len(added)} seeded, {len(already)} already set, {len(invalid)} invalid.")
    finally:
        db.close()


def remove(numbers: list[str]) -> None:
    """Put a number back into normal bot handling."""
    db = SessionLocal()
    try:
        for raw in numbers:
            number = _normalize(raw)
            lead = db.query(Lead).filter_by(wa_number=number).first() if number else None
            if lead is None:
                print(f"  not found  {raw}")
            else:
                lead.human_takeover = False
                print(f"  restored   {number} (bot will qualify them again)")
        db.commit()
    finally:
        db.close()


def show() -> None:
    db = SessionLocal()
    try:
        leads = db.query(Lead).filter_by(human_takeover=True).order_by(Lead.id).all()
        if not leads:
            print("No numbers are currently marked human-only.")
            return
        print(f"{len(leads)} number(s) marked human-only:")
        for lead in leads:
            print(f"  {lead.wa_number}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mark WhatsApp numbers as human-only.")
    parser.add_argument("numbers", nargs="*", help="WhatsApp numbers, e.g. 919820012345")
    parser.add_argument("--file", help="Text file with one number per line")
    parser.add_argument("--list", action="store_true", help="Show numbers already marked")
    parser.add_argument("--remove", action="store_true", help="Unmark the given numbers")
    args = parser.parse_args()

    if args.list:
        show()
        sys.exit(0)

    numbers = list(args.numbers)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            numbers += [line.strip() for line in handle if line.strip() and not line.startswith("#")]

    if not numbers:
        parser.error("Give at least one number, or --file, or --list.")

    remove(numbers) if args.remove else seed(numbers)
