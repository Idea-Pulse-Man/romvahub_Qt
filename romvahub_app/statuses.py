"""Application statuses: the server's list, how each one looks, and the Applications tabs."""

from __future__ import annotations

# The server's statuses, in its order (backend/src/domain/types.ts).
STATUSES = [
    "Draft",
    "Applied",
    "Screening (Round 1)",
    "Interview (Round 2)",
    "Interview (Round 3)",
    "Final Interview",
    "Offer",
    "Background Check Passed",
    "Started",
    "Completed",
    "Failed",
    "Expired",
    "Other",
    "Skip",
]

KIND = {
    "Draft": "draft",
    "Applied": "applied",
    "Screening (Round 1)": "interview",
    "Interview (Round 2)": "interview",
    "Interview (Round 3)": "interview",
    "Final Interview": "interview",
    "Offer": "offer",
    "Background Check Passed": "offer",
    "Started": "offer",
    "Completed": "offer",
    "Failed": "failed",
    "Expired": "failed",
    "Other": "draft",
    "Skip": "draft",
}

# Groups in the status menu (a line before each group).
GROUP_STARTS = {"Applied", "Screening (Round 1)", "Offer", "Failed"}

INTERVIEW_STATUSES = [s for s in STATUSES if KIND[s] in ("interview", "offer")]

# (tab id, label, query): `statuses` and `hasResume` are the list filters.
TABS = [
    ("draft", "Draft", {"statuses": ["Draft"], "hasResume": "false"}),
    ("ready", "Ready to apply", {"statuses": ["Draft"], "hasResume": "true"}),
    ("applied", "Applied", {"statuses": ["Applied"]}),
    ("interview", "Interviews", {"statuses": INTERVIEW_STATUSES}),
    ("all", "All", {}),
]


def display_status(bid: dict) -> tuple[str, str]:
    """(label, kind) of a bid's status chip. A Draft with its Resume made shows as "Ready"."""
    status = str(bid.get("status") or "Draft")
    if status == "Draft" and bid.get("hasResume"):
        return "Ready", "ready"
    return status, KIND.get(status, "draft")
