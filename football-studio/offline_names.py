"""Deterministic, provisional Chinese renderings of football names.

These spelling-based readings are deliberately labelled as unverified by the
caller. They provide a readable fallback, including during an offline session.
The original spelling must remain alongside them in the calling application.
"""
import re
import unicodedata


HAN = re.compile(r"[\u3400-\u9fff]")
COMMON = {
    "football": "足球", "soccer": "足球", "futbol": "足球", "futebol": "足球",
    "club": "俱乐部", "clube": "俱乐部", "fc": "足球俱乐部", "cf": "足球俱乐部",
    "sc": "体育俱乐部", "ac": "竞技俱乐部", "cd": "体育俱乐部",
    "association": "协会", "associacao": "协会", "sport": "体育", "sports": "体育",
    "sporting": "竞技", "athletic": "竞技", "atletico": "竞技", "athletico": "竞技",
    "deportivo": "体育", "esporte": "体育", "esportivo": "体育", "desportivo": "体育",
    "united": "联", "union": "联合", "uniao": "联合", "city": "城", "town": "镇",
    "county": "郡", "rovers": "流浪者", "wanderers": "漫游者", "rangers": "流浪者",
    "real": "皇家", "royal": "皇家", "racing": "竞赛", "national": "全国",
    "nacional": "国民", "international": "国际", "internacional": "国际",
    "saint": "圣", "st": "圣", "sao": "圣", "san": "圣", "santa": "圣",
    "olympic": "奥林匹克", "olympique": "奥林匹克", "olimpico": "奥林匹克",
    "new": "新", "old": "老", "north": "北", "northern": "北部",
    "south": "南", "southern": "南部", "east": "东", "eastern": "东部",
    "west": "西", "western": "西部", "central": "中央", "university": "大学",
    "academy": "学院", "youth": "青年", "junior": "青年", "juniors": "青年",
    "reserves": "预备队", "reserve": "预备队", "men": "男子", "mens": "男子",
    "women": "女子", "womens": "女子", "ladies": "女子", "femenino": "女子",
    "femenina": "女子", "feminino": "女子", "feminina": "女子", "feminin": "女子",
    "frauen": "女子", "femminile": "女子", "boys": "男子青年", "girls": "女子青年",
    "league": "联赛", "liga": "联赛", "ligue": "联赛", "lig": "联赛",
    "cup": "杯", "copa": "杯", "coupe": "杯", "pokal": "杯",
    "championship": "锦标赛", "champions": "冠军", "championnat": "锦标赛",
    "campeonato": "锦标赛", "tournament": "锦标赛", "premier": "超级",
    "premiership": "超级联赛", "super": "超级", "superliga": "超级联赛",
    "elite": "精英", "professional": "职业", "pro": "职业", "amateur": "业余",
    "division": "级别", "divisie": "级别", "divisao": "级别", "serie": "级别",
    "qualifying": "预选赛", "qualification": "资格赛", "qualifiers": "预选赛",
    "preliminary": "预赛", "prelims": "预赛", "playoffs": "附加赛",
    "final": "决赛", "finals": "决赛阶段", "semifinal": "半决赛",
    "semifinals": "半决赛", "quarterfinal": "四分之一决赛", "quarterfinals": "四分之一决赛",
    "group": "组", "stage": "阶段", "phase": "阶段", "round": "轮",
    "regular": "常规", "season": "赛季", "friendly": "友谊赛", "friendlies": "友谊赛",
    "world": "世界", "continental": "洲际",
    "promotion": "升级", "relegation": "降级", "apertura": "开幕赛", "clausura": "闭幕赛",
    "regional": "地区", "region": "地区", "district": "地区", "state": "州", "estadual": "州",
    "metropolitan": "都市", "federation": "足协", "federacao": "足协", "federacion": "足协",
    "first": "第一", "second": "第二", "third": "第三", "fourth": "第四", "fifth": "第五",
    "leg": "回合", "home": "主场", "away": "客场", "aggregate": "总比分",
    "uefa": "欧足联", "fifa": "国际足联", "afc": "亚足联", "caf": "非洲足联",
    "concacaf": "中北美及加勒比足联", "conmebol": "南美足联", "ofc": "大洋洲足联",
    "english": "英格兰", "england": "英格兰", "scottish": "苏格兰", "scotland": "苏格兰",
    "welsh": "威尔士", "wales": "威尔士", "irish": "爱尔兰", "ireland": "爱尔兰",
    "spanish": "西班牙", "spain": "西班牙", "german": "德国", "germany": "德国",
    "french": "法国", "france": "法国", "italian": "意大利", "italy": "意大利",
    "portuguese": "葡萄牙", "portugal": "葡萄牙", "dutch": "荷兰", "netherlands": "荷兰",
    "belgian": "比利时", "belgium": "比利时", "swiss": "瑞士", "switzerland": "瑞士",
    "austrian": "奥地利", "austria": "奥地利", "swedish": "瑞典", "sweden": "瑞典",
    "danish": "丹麦", "denmark": "丹麦", "norwegian": "挪威", "norway": "挪威",
    "finnish": "芬兰", "finland": "芬兰", "icelandic": "冰岛", "iceland": "冰岛",
    "polish": "波兰", "poland": "波兰", "czech": "捷克", "czechia": "捷克",
    "turkish": "土耳其", "turkey": "土耳其", "turkiye": "土耳其", "greek": "希腊",
    "greece": "希腊", "russian": "俄罗斯", "russia": "俄罗斯", "ukrainian": "乌克兰",
    "ukraine": "乌克兰", "brazilian": "巴西", "brazil": "巴西", "brasileiro": "巴西",
    "argentine": "阿根廷", "argentinian": "阿根廷", "argentina": "阿根廷",
    "colombian": "哥伦比亚", "colombia": "哥伦比亚", "chilean": "智利", "chile": "智利",
    "peruvian": "秘鲁", "peru": "秘鲁", "uruguayan": "乌拉圭", "uruguay": "乌拉圭",
    "ecuadorian": "厄瓜多尔", "ecuador": "厄瓜多尔", "paraguayan": "巴拉圭",
    "paraguay": "巴拉圭", "bolivian": "玻利维亚", "bolivia": "玻利维亚",
    "venezuelan": "委内瑞拉", "venezuela": "委内瑞拉", "mexican": "墨西哥", "mexico": "墨西哥",
    "american": "美国", "canadian": "加拿大", "canada": "加拿大",
    "japanese": "日本", "japan": "日本", "chinese": "中国", "china": "中国",
    "korean": "韩国", "korea": "韩国", "indian": "印度", "india": "印度",
    "indonesian": "印度尼西亚", "indonesia": "印度尼西亚", "malaysian": "马来西亚",
    "malaysia": "马来西亚", "thai": "泰国", "thailand": "泰国", "vietnamese": "越南",
    "vietnam": "越南", "australian": "澳大利亚", "australia": "澳大利亚",
    "saudi": "沙特", "arabian": "阿拉伯", "qatar": "卡塔尔", "qatari": "卡塔尔",
    "iranian": "伊朗", "iran": "伊朗", "iraqi": "伊拉克", "iraq": "伊拉克",
    "egyptian": "埃及", "egypt": "埃及", "moroccan": "摩洛哥", "morocco": "摩洛哥",
    "algerian": "阿尔及利亚", "algeria": "阿尔及利亚", "tunisian": "突尼斯", "tunisia": "突尼斯",
    "nigerian": "尼日利亚", "nigeria": "尼日利亚", "ghanaian": "加纳", "ghana": "加纳",
    "european": "欧洲", "african": "非洲", "asian": "亚洲", "caribbean": "加勒比",
}
CONNECTORS = {"de", "da", "do", "das", "dos", "del", "di", "du", "des", "la", "le", "of", "the", "and", "et", "e", "y"}
LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz", ["阿", "布", "克", "德", "埃", "夫", "格", "赫", "伊", "吉", "克", "尔", "姆", "恩", "奥", "普", "克", "尔", "斯", "特", "乌", "夫", "乌", "克斯", "伊", "兹"]))
VOWELS = "aeiou"
SYLLABLES = {
    "b": "巴贝比博布", "c": "卡塞西科库", "d": "达德迪多杜", "f": "法费菲福富",
    "g": "加格吉戈古", "h": "哈赫希霍胡", "j": "贾杰吉乔朱", "k": "卡凯基科库",
    "l": "拉莱利洛卢", "m": "马梅米莫穆", "n": "纳内尼诺努", "p": "帕佩皮波普",
    "q": "卡奎基科库", "r": "拉雷里罗鲁", "s": "萨塞西索苏", "t": "塔特蒂托图",
    "v": "瓦韦维沃武", "w": "瓦韦维沃伍", "x": "扎泽西索苏", "y": "亚耶伊约尤",
    "z": "扎泽齐佐祖",
}
PARTS = {
    "chester": "切斯特", "borough": "伯勒", "shire": "郡", "ville": "维尔",
    "burg": "堡", "berg": "贝格", "ham": "汉姆", "ford": "福德", "ton": "顿",
    "sch": "施", "sh": "什", "ch": "奇", "th": "瑟", "zh": "日", "ph": "夫",
    "ck": "克", "qu": "库", "tz": "茨", "ts": "茨", "nh": "尼", "lh": "利",
    "ng": "恩", "rr": "尔", "ll": "利", "ee": "伊", "ea": "伊", "oo": "乌",
    "ou": "奥", "ai": "艾", "ei": "艾", "au": "奥", "oi": "瓦", "eu": "欧",
    "ie": "耶", "oa": "奥", "io": "约",
}
PART_KEYS = sorted(PARTS, key=len, reverse=True)
SPECIAL_LATIN = str.maketrans({"ß": "ss", "ø": "o", "æ": "ae", "œ": "oe", "ł": "l", "đ": "d", "ð": "dh", "þ": "th", "ı": "i", "ħ": "h"})
CYRILLIC = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяіїєґђјљњћџ", ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya", "i", "yi", "ye", "g", "dj", "j", "lj", "nj", "ch", "dzh"]))
GREEK = dict(zip("αβγδεζηθικλμνξοπρσςτυφχψω", ["a", "v", "g", "d", "e", "z", "i", "th", "i", "k", "l", "m", "n", "ks", "o", "p", "r", "s", "s", "t", "y", "f", "kh", "ps", "o"]))
ARABIC = dict(zip("ابتثجحخدذرزسشصضطظعغفقكلمنهويءؤئىة", ["a", "b", "t", "th", "j", "h", "kh", "d", "dh", "r", "z", "s", "sh", "s", "d", "t", "z", "a", "gh", "f", "q", "k", "l", "m", "n", "h", "w", "y", "a", "w", "y", "a", "h"]))


def _latin(text):
    text = text.casefold().translate(SPECIAL_LATIN)
    chars = []
    for char in unicodedata.normalize("NFKD", text):
        if unicodedata.combining(char):
            continue
        chars.append(CYRILLIC.get(char, GREEK.get(char, ARABIC.get(char, char))))
    return "".join(chars)


def _sound(word):
    word = _latin(word)
    result = []
    pos = 0
    while pos < len(word):
        part = next((part for part in PART_KEYS if word.startswith(part, pos)), None)
        if part:
            result.append(PARTS[part])
            pos += len(part)
        elif word[pos] in SYLLABLES and pos + 1 < len(word) and word[pos + 1] in VOWELS:
            result.append(SYLLABLES[word[pos]][VOWELS.index(word[pos + 1])])
            pos += 2
        else:
            char = word[pos]
            if char in LETTERS:
                result.append(LETTERS[char])
            elif HAN.match(char) or char.isdigit():
                result.append(char)
            else:
                # Unicode syllable/letter names cover many further scripts.
                phoneme = unicodedata.name(char, "").split(" ")[-1].lower()
                if phoneme and re.fullmatch(r"[a-z]+", phoneme):
                    result.append(_sound(phoneme))
                else:
                    result.append(char)
            pos += 1
    return "".join(result)


def transliterate(name, kind="team", context=""):
    """Render spelling and common football words in Chinese, without a network."""
    text = unicodedata.normalize("NFKC", name.strip()).replace("’", "'")
    text = re.sub(r"\b(women|men)'s\b", r"\1", text, flags=re.I)
    text = re.sub(r"\b(?:under[- ]?|u[- ]?)(\d{1,2})\b", lambda m: f" {m[1]}岁以下 ", text, flags=re.I)
    if kind != "team":
        levels = {"a": "甲", "b": "乙", "c": "丙", "d": "丁", "1": "第一", "2": "第二", "3": "第三", "4": "第四", "one": "第一", "two": "第二", "three": "第三"}
        text = re.sub(r"\b(?:serie|series|division|divisao|liga)\s+([abcd1-4]|one|two|three)\b",
                      lambda m: " " + levels[m[1].lower()] + "级联赛 ", text, flags=re.I)
        text = re.sub(r"\b(?:matchday|round)\s+(\d+)\b", r" 第\1轮 ", text, flags=re.I)
        text = re.sub(r"\bgroup\s+([a-z0-9])\b", lambda m: " " + m[1].upper() + "组 ", text, flags=re.I)
        text = re.sub(r"\bsemi[- ]finals?\b", " 半决赛 ", text, flags=re.I)
        text = re.sub(r"\bquarter[- ]finals?\b", " 四分之一决赛 ", text, flags=re.I)
        text = re.sub(r"\bplay[- ]offs?\b", " 附加赛 ", text, flags=re.I)
        text = re.sub(r"\bplay[- ]in\b", " 资格附加赛 ", text, flags=re.I)
    tokens = re.findall(r"[\w]+|[^\w\s]", text, re.UNICODE)
    output = []
    for token in tokens:
        word = _latin(token)
        if word in CONNECTORS and len(tokens) > 1:
            continue
        if not any(char.isalnum() for char in token):
            if token in ("-", "·", "&", "/"):
                output.append("·" if token != "/" else "/")
            continue
        if HAN.search(token):
            output.append(token)
        elif kind == "team" and word == "afc":
            output.append("足球俱乐部")
        elif token.isdigit():
            output.append(token)
        else:
            output.append(COMMON.get(word) or _sound(token))
    result = "".join(output).strip("·/")
    if not HAN.search(result):
        # Pure number or punctuation names retain their own identity visibly.
        digits = str.maketrans("0123456789", "零一二三四五六七八九")
        result = result.translate(digits)
    return result or "".join(_sound(char) for char in text if not char.isspace())
