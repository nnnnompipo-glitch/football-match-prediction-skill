"""Resolve only user-confirmed team names across fixture, rating, result and odds feeds."""


class TeamNames:
    def __init__(self, aliases):
        if not isinstance(aliases, dict):
            raise ValueError("球队别名文件须为显示名到约定队名的 JSON 对象")
        self.names = {}
        for original, canonical in aliases.items():
            if not all(isinstance(x, str) and x.strip() for x in (original, canonical)):
                raise ValueError("球队别名及约定队名须为非空字符串")
            for key in (original, canonical):
                key = key.strip().casefold()
                value = canonical.strip()
                if key in self.names and self.names[key] != value:
                    raise ValueError("同名映射到多个球队，或存在别名链：" + key)
                self.names[key] = value

    def name(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("球队名称必须为非空字符串")
        return self.names.get(value.strip().casefold(), value.strip())

    def row(self, data):
        result = dict(data)
        for field in ("home", "away", "team"):
            if isinstance(data.get(field), str):
                result[field] = self.name(data[field])
        if "evidence" in data and isinstance(data["evidence"], list):
            result["evidence"] = [self.row(event) for event in data["evidence"]]
        return result
