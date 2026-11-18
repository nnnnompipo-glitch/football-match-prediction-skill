"""Estimate goal timing conditional on the final 90-minute score distribution."""
import math


def timing_summary(matrix):
    """Rows are full-time home goals, columns are full-time away goals."""
    if not isinstance(matrix, (list, tuple)) or not matrix:
        raise ValueError("比分矩阵必须有数据")
    if not isinstance(matrix[0], (list, tuple)) or not matrix[0]:
        raise ValueError("比分矩阵的每行须包含客队进球概率")
    width = len(matrix[0])
    for row in matrix:
        if not isinstance(row, (list, tuple)) or len(row) != width:
            raise ValueError("比分矩阵各行长度须一致")
        if any(type(p) not in (int, float) or not 0 <= p <= 1 for p in row):
            raise ValueError("比分概率须为 0 至 1 之间的有限数值")
    mass = math.fsum(math.fsum(row) for row in matrix)
    if not math.isclose(mass, 1, rel_tol=0, abs_tol=1e-8):
        raise ValueError("比分矩阵总概率应为 1")

    # Given n goals in 90 minutes, k first-half goals have probability C(n,k)/2**n.
    # Transform each axis separately to preserve dependence in the full-time scores.
    height = len(matrix)
    half_given_full = [[math.comb(n, k) / (1 << n) for k in range(n + 1)]
                       for n in range(max(height, width))]
    half_home_full_away = [[0.0] * width for _ in range(height)]
    for full_home, row in enumerate(matrix):
        for full_away, prob in enumerate(row):
            if prob:
                for half_home, weight in enumerate(half_given_full[full_home]):
                    half_home_full_away[half_home][full_away] += prob / mass * weight
    half_scores = [[0.0] * width for _ in range(height)]
    for half_home, row in enumerate(half_home_full_away):
        for full_away, prob in enumerate(row):
            if prob:
                for half_away, weight in enumerate(half_given_full[full_away]):
                    half_scores[half_home][half_away] += prob * weight

    half_probs = [0.0, 0.0, 0.0]
    scorelines = []
    for home, row in enumerate(half_scores):
        for away, prob in enumerate(row):
            if prob:
                outcome = 0 if home > away else 1 if home == away else 2
                half_probs[outcome] += prob
                scorelines.append({"home": home, "away": away, "p": prob})
    scorelines.sort(key=lambda item: -item["p"])

    home_goals = math.fsum(h * math.fsum(row) for h, row in enumerate(matrix)) / mass
    away_goals = math.fsum(a * p for row in matrix for a, p in enumerate(row)) / mass
    # A period is empty given n goals with probability (5/6)**n.
    at_least_one = [1 - (5 / 6) ** n for n in range(height + width - 1)]
    one_goal = math.fsum(p * at_least_one[h + a] for h, row in enumerate(matrix)
                         for a, p in enumerate(row)) / mass
    home_one = math.fsum(math.fsum(row) * at_least_one[h] for h, row in enumerate(matrix)) / mass
    away_one = math.fsum(p * at_least_one[a] for row in matrix for a, p in enumerate(row)) / mass
    periods = [{"start_minute": start, "end_minute": start + 15,
                "home_expected_goals": home_goals / 6, "away_expected_goals": away_goals / 6,
                "expected_goals": (home_goals + away_goals) / 6,
                "p_at_least_one_goal": one_goal, "p_home_goal": home_one, "p_away_goal": away_one}
               for start in range(0, 90, 15)]
    return {"assumption": "给定常规时间全场比分后，各进球时刻在90分钟内独立均匀分布。"
                          "六段等长，各段边际概率相同；结果只描述时段分布，不生成进球球员或具体分钟事件。",
            "half_probs": half_probs, "half_top_scores": scorelines[:5],
            "half_expected_goals": [home_goals / 2, away_goals / 2], "periods": periods}
