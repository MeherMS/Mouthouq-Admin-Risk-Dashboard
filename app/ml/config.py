"""Phase 2 settings. All timestamps are naive UTC, matching the Phase 1 notebook."""
import pandas as pd

SIM_END = pd.Timestamp("2026-11-15")   # simulation end (generator window ends here)
HORIZON_DAYS = 90                      # label window after each cutoff

MISSED_EVENT = "missed"
TROUBLE_EVENTS = ("late", "partial", "missed")

# Monthly snapshots. The last cutoff must leave a full HORIZON_DAYS window before SIM_END.
CUTOFFS = [
    pd.Timestamp(d)
    for d in [
        "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01",
        "2026-06-01", "2026-07-01", "2026-08-01",
    ]
]