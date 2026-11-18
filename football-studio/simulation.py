"""Sample a 90-minute score and create illustrative highlights from a forecast."""

import math
import random
import secrets

import model


def _number(value, low, high, name):
    if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} 超出范围或不是数字")
    return value


def _distribution(prediction):
    """Use the skill's Dixon–Coles matrix and its within-outcome proportions."""
    means = prediction["model_goal_means"]
    probs = prediction["probs"]
    if not isinstance(means, list) or len(means) != 2:
        raise ValueError("模拟需要双方的模型进球均值")
    if not isinstance(probs, list) or len(probs) != 3:
        raise ValueError("模拟需要主胜、平局、客胜三个概率")
    means = [_number(x, 0.05, 8, "进球均值") for x in means]
    probs = [_number(x, 0, 1, "胜平负概率") for x in probs]
    if not math.isclose(sum(probs), 1.0, abs_tol=1e-8):
        raise ValueError("胜平负概率之和须为 1")
    rho = _number(prediction["rho_used"], -0.2, 0.2, "低比分修正系数")
    base_matrix, _ = model._matrix(means, rho)
    baseline = model._probabilities(base_matrix)
    scale = [p / b for p, b in zip(probs, baseline)]
    return [[mass * scale[model._outcome(h, a)] for a, mass in enumerate(row)]
            for h, row in enumerate(base_matrix)]


def _choose_score(matrix, selection, rng):
    if isinstance(selection, list) and len(selection) == 2:
        home, away = selection
        if (type(home) is not int or type(away) is not int
                or not 0 <= home < len(matrix) or not 0 <= away < len(matrix[home])
                or matrix[home][away] <= 0):
            raise ValueError("所选比分不在本场预测分布内")
        return home, away
    if selection not in ("most_likely", "sample"):
        raise ValueError("请选择最高概率比分、候选比分或概率抽样")
    cells = [(h, a) for h, row in enumerate(matrix) for a in range(len(row))]
    if selection == "most_likely":
        return max(cells, key=lambda cell: matrix[cell[0]][cell[1]])
    weights = [matrix[h][a] for h, a in cells]
    return rng.choices(cells, weights=weights, k=1)[0]


def _highlights(score, expected, rng):
    # Generate visual sequences after the score is sampled. These are simulated
    # actions, not independent shots predictions or claims about real players.
    total_xg = sum(expected)
    home_share = expected[0] / total_xg
    goal_sides = ["home"] * score[0] + ["away"] * score[1]
    open_minutes = [m for m in range(1, 90) if m != 45]
    goal_minutes = rng.sample(open_minutes, len(goal_sides))
    events = [{"minute": m, "side": side, "type": "goal"}
              for m, side in zip(goal_minutes, goal_sides)]
    free_minutes = sorted(set(open_minutes).difference(goal_minutes))
    extra_count = min(len(free_minutes), min(18, 5 + round(1.6 * total_xg)) + rng.randrange(3))
    chance_minutes = sorted(rng.sample(free_minutes, extra_count))
    # Both teams take part in build-up and defensive play, even in a 0–0 draw.
    sides = ["home", "away"] + [
        "home" if rng.random() < home_share else "away" for _ in range(max(0, extra_count - 2))]
    rng.shuffle(sides)
    actions = ("save", "miss", "tackle", "attack", "pass")
    for minute, side in zip(chance_minutes, sides):
        action = rng.choices(actions, weights=(4, 3, 2, 2, 1))[0]
        if action == "tackle":
            side = "away" if side == "home" else "home"
        events.append({"minute": minute, "side": side, "type": action})
    opening = rng.choice(["home", "away"])
    events.extend([{"minute": 0, "side": opening, "type": "kickoff"},
                   {"minute": 45, "type": "halftime"},
                   {"minute": 90, "type": "fulltime"}])
    return sorted(events, key=lambda event: event["minute"])


def simulate(payload):
    home, away = payload["home"], payload["away"]
    if not all(isinstance(team, str) and team.strip() for team in (home, away)) or home == away:
        raise ValueError("比赛模拟需要两个不同的队名")
    prediction = payload["prediction"]
    seed = payload.get("seed", None)
    if seed is None:
        seed = secrets.randbits(32)
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("随机种子须为无符号 32 位整数")
    rng = random.Random(seed)
    matrix = _distribution(prediction)
    selection = payload.get("selection", "most_likely")
    h, a = _choose_score(matrix, selection, rng)
    expected = [sum(i * sum(row) for i, row in enumerate(matrix)),
                sum(j * p for row in matrix for j, p in enumerate(row))]
    return {"home": home, "away": away, "score": [h, a], "seed": seed,
            "selection": selection, "score_probability": matrix[h][a], "probs": prediction["probs"],
            "expected_goals": expected, "events": _highlights((h, a), expected, rng)}
