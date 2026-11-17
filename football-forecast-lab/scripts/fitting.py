"""Fit venue-adjusted attack/defence factors with weighted Poisson likelihood."""
import math
from model import _records
from workflow import instant


def fit_strength(rows, as_of, competition=None):
    cutoff = instant(as_of)
    labels = {r.get("competition") or r.get("league") for r in rows}
    if competition is None:
        named = labels - {None}
        if len(named) > 1:
            raise ValueError("历史含多个赛事，请用 --competition 指定")
        competition = next(iter(named), None)
    if competition:
        rows = [r for r in rows if (r.get("competition") or r.get("league")) == competition]
    data, ignored = _records(rows, cutoff, competition)
    if len(data) < 20:
        raise ValueError("拟合至少需要 20 场截点前可用的常规时间比分")
    weighted = sum(r[-1] for r in data if not r[4])
    home_mean = (sum(r[2]*r[-1] for r in data if not r[4]) + 8*1.45)/(weighted+8)
    away_mean = (sum(r[3]*r[-1] for r in data if not r[4]) + 8*1.15)/(weighted+8)
    neutral_weight = sum(r[-1] for r in data if r[4])
    neutral_mean = (sum((r[2]+r[3])*r[-1] for r in data if r[4]) + 16*1.30)/(2*neutral_weight+16)
    names = sorted({t for h,a,*_ in data for t in (h,a)})
    teams = {t: [1.,1.] for t in names}
    games = [(h,a,hg,ag,neutral_mean if neutral else home_mean,neutral_mean if neutral else away_mean,w)
             for h,a,hg,ag,neutral,w in data]
    # Alternating penalized Poisson likelihood updates. The rate-ratio prior is centred at one.
    for iteration in range(1,101):
        largest = 0.
        for column in (0,1):
            observed = {t:6. for t in teams}
            exposure = {t:6. for t in teams}
            for h,a,hg,ag,rh,ra,w in games:
                for attacking,defending,goals,base in ((h,a,hg,rh),(a,h,ag,ra)):
                    team = defending if column else attacking
                    other = attacking if column else defending
                    observed[team] += w*goals
                    exposure[team] += w*base*teams[other][1-column]
            for t in teams:
                val = observed[t]/exposure[t]
                largest = max(largest, abs(val - teams[t][column]))
                teams[t][column] = val
        if largest < 0.00001:
            break
    # For fixed means the independent Poisson terms are constant in rho.
    pairs = [(min(8,max(.05,rh*teams[h][0]*teams[a][1])),
              min(8,max(.05,ra*teams[a][0]*teams[h][1])),hg,ag,w)
             for h,a,hg,ag,rh,ra,w in games]
    def score(rho):
        likelihood = -8*rho*rho
        for h,a,hg,ag,w in pairs:
            factors = {(0,0):1-h*a*rho,(1,0):1+a*rho,(0,1):1+h*rho,(1,1):1-rho}
            if min(factors.values()) <= 0:
                return -math.inf
            likelihood += w*math.log(factors.get((hg,ag),1.))
        return likelihood
    rho = max((k/100 for k in range(-18,19)),key=score)
    return {"schema":"football-forecast-lab/strength-v1","competition":competition,"as_of":cutoff.isoformat(),
            "matches":len(data),"ignored":ignored,"iterations":iteration,"half_life_days":180,
            "home_mean":home_mean,"away_mean":away_mean,"neutral_mean":neutral_mean,"rho":rho,
            "teams":{t:{"attack":v[0],"concession":v[1]} for t,v in teams.items()}}


def attach_fit(match, fit):
    if fit.get("schema") != "football-forecast-lab/strength-v1":
        raise ValueError("模型文件格式错误")
    if instant(fit["as_of"]) > instant(match["as_of"]):
        raise ValueError("拟合时间晚于预测截点")
    if fit.get("competition") and fit["competition"] != (match.get("competition") or match.get("league")):
        raise ValueError("拟合赛事与输入赛事不一致")
    for k in ("home_xg", "away_xg"):
        if match.get(k) is not None:
            raise ValueError("显式预期进球与 --fit 同时提供，请选择一种进球均值来源")
    try:
        home, away = fit["teams"][match["home"]], fit["teams"][match["away"]]
    except KeyError as exc:
        raise ValueError("拟合文件中找不到参赛球队；可移除 --fit 以使用评级／先验路径") from exc
    rh, ra = (fit["neutral_mean"],)*2 if match.get("neutral") else (fit["home_mean"],fit["away_mean"])
    result = dict(match)
    for team,mean in (("home",rh*home["attack"]*away["concession"]),("away",ra*away["attack"]*home["concession"])):
        if not math.isfinite(mean) or mean <= 0:
            raise ValueError("模型的进球均值无效")
        result[team+"_xg"] = min(8.,max(.05,mean))
    result["xg_at"] = fit["as_of"]
    result.setdefault("rho",fit["rho"])
    result["fit_provenance"] = {k:fit[k] for k in ("schema","competition","as_of","matches","rho")}
    return result
