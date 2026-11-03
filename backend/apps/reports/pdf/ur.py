"""
LAB-29 (KAN-154): fixed Urdu strings for the patient summary block (§9.2).

These are tenant-level fixed texts, never free-typed clinical content.
A later step may override them per-tenant via notification_template (ur);
until then this module is the single source.
"""

from __future__ import annotations

# "Your report is ready" — fixed patient-usability sentence.
REPORT_READY_UR = "آپ کی رپورٹ تیار ہے"

# "For questions, please contact" — fixed lead-in for the lab phone.
QUESTIONS_CALL_UR = "سوالات کے لیے رابطہ کریں"
