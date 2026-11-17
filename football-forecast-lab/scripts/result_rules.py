"""Shared contracts for regulation results and three-way forecast evaluation."""
import math


def require_final_regulation(row):
    """An unlabelled score is a manual regulation result. Validate any supplied labels."""
    if row.get("market", "1x2_90") != "1x2_90":
        raise ValueError("只接受常规时间（1x2_90）赛果")
    regulation = {"90", "90_MIN", "REGULAR", "REGULAR_TIME", "REGULATION", "NORMAL_TIME", "1X2_90"}
    if "score_period" in row and str(row["score_period"]).strip().upper() not in regulation:
        raise ValueError("进球数字段的时段必须是常规时间")
    explicit_regulation = row.get("market") == "1x2_90" or "score_period" in row
    if "status" in row:
        status = str(row["status"]).strip().upper().replace("-", "_").replace(" ", "_")
        completed = {"FINISHED", "FT", "FINAL", "FULL_TIME", "COMPLETED"}
        after_regulation = {"AET", "PEN", "FT_PEN", "AFTER_EXTRA_TIME", "AFTER_PENALTIES"}
        if status not in completed and not (explicit_regulation and status in after_regulation):
            raise ValueError("只接受已完赛的常规时间赛果，请核实 status 和比分时段")
    if "duration" in row and str(row["duration"]).strip().upper() not in regulation and not explicit_regulation:
        raise ValueError("含加时或点球的比赛须明确标记所提供的比分是常规时间比分")


def top_tie_credit(probs, actual):
    """Expected top-one hit under a uniform tie-break among equally likely outcomes."""
    top = max(probs)
    tied = [i for i, value in enumerate(probs) if math.isclose(value, top, rel_tol=0, abs_tol=1e-12)]
    return (1.0 / len(tied) if actual in tied else 0.0), len(tied) > 1
