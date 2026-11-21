from flask import Flask, render_template, request, jsonify
import os
import json
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.model_selection import train_test_split

app = Flask(__name__)

# ─────────────────────────────────────────────
# [실제 데이터] 출처는 화면과 설명서에 함께 표시할 것
# 주민등록인구 51,117,378명 (행정안전부, 2025.12.31 기준)
DEFAULT_POPULATION = 51_117_378
# 처분가능소득 기준 지니계수 0.325 (국가데이터처 「2025년 가계금융복지조사」, 2024년 소득 기준)
BASE_GINI = 0.325
# 노년부양비 = 고령인구 비중 20.7% ÷ 생산연령인구 비중 69.2% x 100 ≈ 29.9
# (국가데이터처 「2025년 인구주택총조사 등록센서스」)
BASE_AGING_RATIO = 29.9
# ─────────────────────────────────────────────

SCENARIOS = ["steady", "innovation", "aging", "crisis"]
SCENARIO_NAMES = {"steady": "안정 성장", "innovation": "기술 혁신", "aging": "고령화 대응", "crisis": "위기 대응"}
MODES = ["equal", "basic", "custom", "targeted"]  # 하위 계층 집중 정도 순서
MODE_NAMES = {"equal": "동일 분배", "basic": "기본 소득형", "custom": "맞춤형", "targeted": "집중 지원"}
GRADES = ["악화", "유지", "개선"]  # 나쁜 것 → 좋은 것 순서


def get_scenario_config(name):
    config = {
        "steady": {"growth": 1.0, "aging": 1.0, "stability": 1.0},
        "innovation": {"growth": 1.25, "aging": 0.9, "stability": 1.08},
        "aging": {"growth": 0.88, "aging": 1.4, "stability": 0.92},
        "crisis": {"growth": 0.72, "aging": 1.2, "stability": 0.8},
    }
    return config.get(name, config["steady"])


# 분배 방식별 가중치 (i = 0 이 가장 소득이 낮은 1구간)
# 하위 계층 집중 정도: 동일 분배 < 기본 소득형 < 맞춤형 < 집중 지원
def get_distribution_weights(stages, mode):
    if mode == "equal":
        return [1.0 for _ in range(stages)]
    if mode == "basic":
        return [1.0 + (stages - i) * 0.25 for i in range(stages)]
    if mode == "custom":
        return [float(stages - i) for i in range(stages)]
    if mode == "targeted":
        return [float((stages - i) ** 2) for i in range(stages)]
    return [1.0 + (stages - i) * 0.25 for i in range(stages)]


# 분배 집중도 = 1구간(최하위) 비율 - 마지막 구간(최상위) 비율
def get_focus_score(distribution_ratios):
    if len(distribution_ratios) < 2:
        return 0.0
    return distribution_ratios[0] - distribution_ratios[-1]


# 2035년 지니계수로 정책 등급을 정한다 (AI가 학습할 정답)
def get_grade(final_gini):
    if final_gini <= BASE_GINI:
        return "개선"      # 지금(0.325)보다 불평등이 줄어듦
    if final_gini <= BASE_GINI + 0.05:
        return "유지"      # 조금 늘었지만 0.375 이하
    return "악화"          # 0.375보다 커짐


def run_simulation(initial_profit, stages, tax_rate, population, scenario, distribution_mode):
    """시뮬레이션 계산만 담당하는 함수 (웹 화면과 AI 학습에서 함께 사용)"""
    scenario_cfg = get_scenario_config(scenario)
    weights = get_distribution_weights(stages, distribution_mode)
    total_weight = sum(weights)
    distribution_ratios = [w / total_weight for w in weights]

    focus_score = get_focus_score(distribution_ratios)
    distribution_efficiency = 1.0 + focus_score

    years = [str(year) for year in range(2026, 2036)]
    chart_profit, chart_tax, chart_gini = [], [], []

    current_profit = initial_profit
    base_gini = BASE_GINI
    tax_rate = min(0.55, max(0.08, tax_rate))
    effective_rate = tax_rate

    for idx, _year in enumerate(years):
        if idx > 0:
            current_profit *= (1.10 + (scenario_cfg["growth"] - 1.0) * 0.20)
            base_gini = min(0.62, base_gini + 0.012 * scenario_cfg["aging"])

        effective_rate = min(0.50, max(0.08, tax_rate * (1.0 + (scenario_cfg["stability"] - 1.0) * 0.25)))
        total_tax = current_profit * effective_rate

        # 지니계수 감소량 = (세수 / 초기 이익) x 0.10 x 분배 효율
        gini_reduction = (total_tax / max(initial_profit, 1.0)) * 0.10 * distribution_efficiency
        simulated_gini = max(0.20, base_gini - gini_reduction)

        chart_profit.append(round(current_profit, 1))
        chart_tax.append(round(total_tax, 1))
        chart_gini.append(round(simulated_gini, 3))

    last_year_tax = chart_tax[-1] * 1_000_000_000
    stage_results = []
    for i in range(stages):
        stage_total_budget = last_year_tax * distribution_ratios[i]
        stage_people = population * (1.0 / stages)
        per_capita_payout = round((stage_total_budget / stage_people) / 10000, 1)
        start_pct = round(i * (100 / stages))
        end_pct = round((i + 1) * (100 / stages))
        stage_results.append({
            "stage_name": f"{i + 1}구간 (하위 {start_pct}~{end_pct}%)",
            "ratio": round(distribution_ratios[i] * 100, 1),
            "amount": per_capita_payout,
        })

    final_gini = chart_gini[-1]
    social_stability = max(30, min(96, 92 - (final_gini * 60) + (effective_rate * 35) + (scenario_cfg["stability"] * 8)))
    welfare_coverage = max(35, min(95, 42 + (effective_rate * 50) + (scenario_cfg["stability"] * 10) + (focus_score * 20)))
    aging_ratio = max(15, min(60, BASE_AGING_RATIO + (scenario_cfg["aging"] - 1.0) * 16))

    social_impact = [
        {
            "label": "소득 불균형",
            "value": f"{final_gini:.2f}",
            "note": "지니계수",
            "reason": f"2035년 지니계수는 현재 기준 {BASE_GINI:.3f}에서 시작해 매년 변화합니다. 선택한 세율과 분배 방식의 집중도에 따라 세수로 불평등을 얼마나 줄였는지가 최종 값에 반영됐습니다.",
        },
        {
            "label": "사회 안정도",
            "value": f"{social_stability:.0f}/100",
            "note": "국민 체감 지수",
            "reason": f"소득 불균형({final_gini:.3f}), 적용 세율({effective_rate * 100:.1f}%), 경제 시나리오의 안정성으로 계산했습니다. 불평등이 낮고 세수가 안정적일수록 이 지표가 높습니다.",
        },
        {
            "label": "고령화 부담",
            "value": f"{aging_ratio:.1f}%",
            "note": "노년부양비",
            "reason": f"기본 노년부양비 {BASE_AGING_RATIO:.1f}%에 선택한 경제 시나리오의 고령화 계수를 반영해 계산했습니다. 고령화 대응 시나리오를 선택하면 노인 부양 부담이 더 높게 나타납니다.",
        },
        {
            "label": "복지 커버리지",
            "value": f"{welfare_coverage:.0f}%",
            "note": "기본소득/복지",
            "reason": f"세율({effective_rate * 100:.1f}%), 시나리오 안정성, 선택한 분배 방식의 하위계층 집중도를 함께 반영했습니다. 취약계층에 예산을 더 집중할수록 커버리지 상승 폭이 커질 수 있습니다.",
        },
    ]

    return {
        "years": years,
        "profit": chart_profit,
        "tax": chart_tax,
        "gini": chart_gini,
        "stages_data": stage_results,
        "last_tax": round(chart_tax[-1], 1),
        "last_rate": round(effective_rate * 100, 1),
        "focus_score": round(focus_score, 3),
        "final_gini": final_gini,
        "social_impact": social_impact,
    }


# ═════════════════════════════════════════════
# [AI 리포트] 의사결정나무 AI (단기·장기 2그루)
# 1) 시뮬레이터를 여러 조건으로 돌려 학습 데이터를 만든다.
# 2) 단기(2030년) 등급과 장기(2035년) 등급을 각각 예측하는 나무 2그루를 학습한다.
#    (2026년은 모든 조건에서 '개선'이라 배울 것이 없어서, 5년 뒤인 2030년을 단기로 정함)
# 3) 사용자의 조건을 넣으면 두 등급을 예측하고, 판단 근거와 함께 리포트를 만든다.
# ═════════════════════════════════════════════
SHORT_YEAR_INDEX = 4      # years[4] = 2030년 (단기)
LONG_YEAR_INDEX = -1      # years[-1] = 2035년 (장기)
FEATURE_NAMES = ["세율", "분배 방식", "계층 수"] + [f"시나리오_{SCENARIO_NAMES[s]}" for s in SCENARIOS]


def make_features(tax_percent, mode, stages, scenario):
    # 분배 방식은 하위 계층 집중 순서대로 0~3 숫자로 바꾼다
    scenario_onehot = [1 if scenario == s else 0 for s in SCENARIOS]
    return [tax_percent, MODES.index(mode), stages] + scenario_onehot


def train_ai_models():
    X, y_short, y_long = [], [], []
    for tax_percent in range(8, 56):          # 세율 8~55%
        for scenario in SCENARIOS:             # 시나리오 4가지
            for mode in MODES:                 # 분배 방식 4가지
                for stages in range(2, 11):    # 계층 2~10단계
                    result = run_simulation(1000, stages, tax_percent / 100, DEFAULT_POPULATION, scenario, mode)
                    X.append(make_features(tax_percent, mode, stages, scenario))
                    y_short.append(get_grade(result["gini"][SHORT_YEAR_INDEX]))
                    y_long.append(get_grade(result["gini"][LONG_YEAR_INDEX]))

    models = {}
    for key, y in (("short", y_short), ("long", y_long)):
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        # 깊이를 4로 제한해 사람이 읽을 수 있는 규칙으로 만든다
        model = DecisionTreeClassifier(max_depth=4, random_state=42)
        model.fit(X_train, y_train)
        models[key] = {"model": model, "accuracy": model.score(X_test, y_test)}
    return models, len(X)


AI_MODELS, AI_DATA_SIZE = train_ai_models()


def describe_condition(feature_index, threshold, go_left):
    """나무의 갈림길 조건을 쉬운 한국어 문장으로 바꾼다"""
    name = FEATURE_NAMES[feature_index]
    if name == "세율":
        return f"세율이 {threshold:.1f}% {'이하' if go_left else '초과'}"
    if name == "계층 수":
        return f"계층이 {int(threshold)}단계 {'이하' if go_left else '초과'}"
    if name == "분배 방식":
        cut = int(threshold)  # 이 번호까지가 왼쪽
        group = MODES[:cut + 1] if go_left else MODES[cut + 1:]
        return "분배 방식이 " + "·".join(MODE_NAMES[m] for m in group)
    scenario_name = name.replace("시나리오_", "")
    return f"시나리오가 '{scenario_name}'" + ("이 아님" if go_left else "")


def get_decision_path(model, features):
    tree = model.tree_
    node, steps = 0, []
    while tree.children_left[node] != -1:   # 잎(leaf)에 도착할 때까지
        f, t = tree.feature[node], tree.threshold[node]
        go_left = features[f] <= t
        steps.append(describe_condition(f, t, go_left))
        node = tree.children_left[node] if go_left else tree.children_right[node]
    return steps


def get_feature_importance(model):
    importance = {"세율": 0.0, "분배 방식": 0.0, "계층 수": 0.0, "경제 시나리오": 0.0}
    for name, value in zip(FEATURE_NAMES, model.feature_importances_):
        key = "경제 시나리오" if name.startswith("시나리오_") else name
        importance[key] += value
    ranked = sorted(importance.items(), key=lambda kv: kv[1], reverse=True)
    return [{"factor": k, "percent": round(v * 100, 1)} for k, v in ranked]


def predict_grade(key, tax_percent, mode, stages, scenario):
    model = AI_MODELS[key]["model"]
    features = make_features(tax_percent, mode, stages, scenario)
    grade = model.predict([features])[0]
    probability = max(model.predict_proba([features])[0])
    return grade, probability, features


def make_suggestions(tax_percent, mode, stages, scenario, current_grade):
    """조건을 조금씩 바꿔 보며 장기(2035년) 등급이 좋아지는 방법을 찾는다"""
    candidates = []
    for plus in (5, 10):
        new_tax = min(55, tax_percent + plus)
        if new_tax != tax_percent:
            candidates.append((f"세율을 {new_tax:g}%로 올리면", new_tax, mode))
    if MODES.index(mode) < len(MODES) - 1:
        next_mode = MODES[MODES.index(mode) + 1]
        candidates.append((f"분배 방식을 '{MODE_NAMES[next_mode]}'으로 바꾸면", tax_percent, next_mode))

    suggestions = []
    for text, new_tax, new_mode in candidates:
        grade, _, _ = predict_grade("long", new_tax, new_mode, stages, scenario)
        if GRADES.index(grade) > GRADES.index(current_grade):
            particle = "으로" if grade == "개선" else "로"
            suggestions.append(f"{text} 장기 등급이 '{grade}'{particle} 좋아질 것으로 예측돼요.")
    return suggestions


GRADE_TEXT = {
    "개선": "불평등이 지금보다 줄어들",
    "유지": "불평등이 조금 커지는 수준에 머물",
    "악화": "불평등이 크게 커질",
}


def make_summary(short_grade, long_grade):
    """단기·장기 예측을 한 문장으로 정리한다"""
    if short_grade == long_grade:
        return f"이 정책은 단기(2030년)와 장기(2035년) 모두 {GRADE_TEXT[long_grade]} 것으로 예상돼요."
    sentence = (f"이 정책은 단기적으로(2030년) {GRADE_TEXT[short_grade]}지만, "
                f"장기적으로(2035년)는 {GRADE_TEXT[long_grade]} 것으로 예상돼요.")
    if GRADES.index(short_grade) > GRADES.index(long_grade):
        sentence += " 시뮬레이터에서는 고령화로 지니계수가 해마다 조금씩 커지기 때문에, 시간이 지나면 효과가 약해지는 부작용이 있어요."
    return sentence


def make_future_event(tax_percent, mode, stages, scenario):
    """시나리오와 정책 강도를 바탕으로 미래 경제 전환점을 보여 준다."""
    event_by_scenario = {
        "innovation": (
            "AI 자동화와 생산성 혁신이 가속되어 노동시장 구조가 빠르게 재편될 가능성",
            "기술 투자 확대 시나리오에서는 AI 활용 기업의 이익과 산업 생산성이 크게 늘 것으로 가정합니다.",
        ),
        "aging": (
            "고령 인구 증가로 돌봄·의료 수요가 급증하고 노동력 부족이 본격화될 가능성",
            "고령화 대응 시나리오에서는 부양 부담이 커지고 사회서비스 산업이 성장하도록 가정합니다.",
        ),
        "crisis": (
            "경기 침체와 소비 위축이 이어져 재정 부담과 실업률 상승이 동시 발생할 가능성",
            "위기 대응 시나리오에서는 경제 성장률이 낮아지는 대신 취약계층 지원 필요성이 커집니다.",
        ),
        "steady": (
            "AI 세수와 복지 지출이 균형을 이루며 공공투자와 소비가 안정적으로 확대될 가능성",
            "안정 성장 시나리오에서는 경제와 복지 변화가 완만하게 나타나도록 가정합니다.",
        ),
    }
    event, reason = event_by_scenario.get(scenario, event_by_scenario["steady"])
    concentration_year = 2029
    if tax_percent >= 35:
        concentration_year = 2028
    elif mode in ("targeted", "custom") or stages >= 7:
        concentration_year = 2029
    else:
        concentration_year = 2030
    return {
        "year": concentration_year,
        "event": event,
        "reason": reason,
    }


def build_period_report(key, tax_percent, mode, stages, scenario, actual_grade):
    grade, probability, features = predict_grade(key, tax_percent, mode, stages, scenario)
    model = AI_MODELS[key]["model"]
    return {
        "year": "2030" if key == "short" else "2035",
        "predicted_grade": grade,
        "confidence": round(probability * 100, 1),
        "actual_grade": actual_grade,
        "is_match": grade == actual_grade,
        "decision_path": get_decision_path(model, features),
        "important_factors": get_feature_importance(model),
        "model_accuracy": round(AI_MODELS[key]["accuracy"] * 100, 1),
    }


def build_ai_report(tax_percent, mode, stages, scenario, actual_short, actual_long):
    short_report = build_period_report("short", tax_percent, mode, stages, scenario, actual_short)
    long_report = build_period_report("long", tax_percent, mode, stages, scenario, actual_long)

    suggestions = make_suggestions(tax_percent, mode, stages, scenario, long_report["predicted_grade"])
    if not suggestions and long_report["predicted_grade"] != "개선":
        suggestions.append("세율이나 분배 방식을 조금 바꿔도 장기 등급은 크게 달라지지 않을 것으로 예측돼요.")

    return {
        "summary": make_summary(short_report["predicted_grade"], long_report["predicted_grade"]),
        "short_term": short_report,
        "long_term": long_report,
        "future_event": make_future_event(tax_percent, mode, stages, scenario),
        "suggestions": suggestions,
        "training_size": AI_DATA_SIZE,
        "grade_rule": "지니계수가 0.325(현재) 이하면 '개선', 0.375 이하면 '유지', 그보다 크면 '악화'",
        "notice": "이 리포트는 시뮬레이터 결과를 학습한 의사결정나무 AI의 예측이에요. "
                  "AI는 틀릴 수 있고, 시뮬레이터의 계산식에는 가정값이 들어 있어 실제 정책 효과와 다를 수 있어요. "
                  "최종 판단은 사람이 직접 해 주세요.",
    }


@app.route('/')
def index():
    return render_template('index.html')


def make_local_ai_answer(question, context):
    """시뮬레이션 데이터와 의사결정나무 결과를 바탕으로 질문에 답한다."""
    text = question.strip().replace("?", "").replace("!", "")
    compact = text.lower().replace(" ", "")
    ai_report = context.get("ai_report", {}) if isinstance(context, dict) else {}
    short_term = ai_report.get("short_term", {})
    long_term = ai_report.get("long_term", {})
    future_event = ai_report.get("future_event", {})
    population = context.get("population")
    tax_list = context.get("tax") or []
    gini_list = context.get("gini") or []
    tax = tax_list[-1] if tax_list else context.get("tax_rate")
    gini = gini_list[-1] if gini_list else context.get("final_gini")
    tax_percent = context.get("tax_rate")
    mode = context.get("distribution_mode", "-")
    scenario = context.get("scenario", "-")
    stages = context.get("stages")
    initial_profit = context.get("initial_profit")
    mode_names = {"equal": "동일 분배", "basic": "기본소득형", "custom": "맞춤형", "targeted": "집중 지원"}
    mode_name = mode_names.get(mode, mode)
    scenario_names = {"steady": "안정 성장", "innovation": "기술 혁신", "aging": "고령화 대응", "crisis": "위기 대응"}
    scenario_name = scenario_names.get(scenario, scenario)

    if any(word in compact for word in ("2030", "단기")) or ("예측" in compact and "2035" not in compact):
        grade = short_term.get("predicted_grade", "-")
        confidence = short_term.get("confidence", "-")
        path = " → ".join(short_term.get("decision_path", []))
        factors = short_term.get("important_factors", [])
        factor_text = ", ".join(f"{item['factor']} {item['percent']}%" for item in factors[:3])
        return (
            f"2030년 예측은 '{grade}'이며, AI 예측 신뢰도는 {confidence}%입니다. "
            f"이 예측은 의사결정나무가 세율 {tax_percent}%, {mode_name}, "
            f"{stages}계층, {scenario_name} 시나리오를 따라내려간 결과입니다.\n"
            f"핸들 기준 경로: {path or '특정 갈림길 정보가 없습니다.'}\n"
            f"가장 영향을 준 요인: {factor_text or '집계 정보 없음'}."
        )
    if any(word in compact for word in ("2035", "장기")):
        grade = long_term.get("predicted_grade", "-")
        suggestions = long_term.get("suggestions", [])
        answer = (
            f"2035년 장기 예측은 '{grade}'이며, 신뢰도는 {long_term.get('confidence', '-')}%입니다. "
            f"해당 시점의 지니계수는 {gini:.3f}이고 예상 세수는 약 {tax:.1f}억원입니다."
        )
        if suggestions:
            answer += "\n개선 방향: " + " ".join(suggestions[:2])
        return answer
    if any(word in compact for word in ("좋은개선안", "개선안", "추천", "어떻게하면")):
        suggestions = ai_report.get("suggestions", [])
        if suggestions:
            return "가장 현실적인 개선안은 다음과 같습니다.\n- " + "\n- ".join(suggestions)
        if long_term.get("predicted_grade") == "개선":
            return "현재 정책은 장기 예측이 '개선'입니다. 세율과 분배 방식을 극단적으로 바꾸기보다 세율을 낮추거나 올릴 때 지표가 어떻게 변하는지 비교하는 것이 좋습니다."
        return "세율을 높이거나 분배 방식을 하위계층에 더 집중하면 장기 개선 가능성을 높일 수 있습니다. 다만 시뮬레이터의 가정 범위 안에서만 판단해 주세요."
    if any(word in compact for word in ("분배방식", "분배", "배당", "지원")):
        if any(word in compact for word in ("차이", "비교", "바꾸")):
            return (
                f"현재는 '{mode_name}'입니다.\n"
                "• 동일 분배: 전 국민에게 같은 비중으로 배분\n"
                "• 기본소득형: 하위계층에 약간 더 배분\n"
                "• 맞춤형: 소득 구간별로 차등 배분\n"
                "• 집중 지원: 취약계층에 예산을 강하게 집중\n"
                "하위계층 집중도가 커질수록 불평등 완화는 강해질 수 있지만 재정 부담도 커질 수 있습니다."
            )
        return (
            f"현재 분배 방식은 '{mode_name}'이고 계층 수는 {stages}단계입니다. "
            "동일 분배는 각 계층에 같은 비중을 두고, 맞춤형과 집중 지원은 하위 계층에 더 많은 비중을 둡니다."
        )
    if any(word in compact for word in ("세율", "세금")):
        message = (
            f"현재 세율은 {tax_percent}%이고, 초기 기업 이익은 {initial_profit:,}억원입니다.\n"
            f"2035년 예상 세수는 약 {tax:.1f}억원이며 지니계수는 {gini:.3f}입니다.\n"
            "세율을 높이면 세수와 재분배 재원이 커질 수 있지만 경제 성장이나 기업 이익에 부담을 줄 수 있습니다."
        )
        if "올리" in compact or "높" in compact:
            return message + "\n세율을 올릴 때는 세수 증가와 불평등 완화 효과가 커지는지 두 지표를 함께 확인하는 것이 좋습니다."
        if "내리" in compact or "낮" in compact:
            return message + "\n세율을 낮추면 기업 부담은 줄 수 있지만 배분 재원과 복지 커버리지가 감소할 수 있습니다."
        return message
    if any(word in compact for word in ("인구", "국민", "사람")):
        if isinstance(population, int):
            per_person = context.get("stages_data")
            extra = ""
            if per_person:
                extra = f" 예를 들어 현재 1구간 배당금은 연 {per_person[0].get('amount', '-'):,}만원입니다."
            return f"현재 적용된 주민등록 인구는 {population:,}명이며, 시민 1인당 배당금 계산에 사용됩니다." + extra
        return "현재 시뮬레이션의 인구수가 아직 결과에 포함되지 않았습니다."
    if any(word in compact for word in ("지표", "안정도", "불균형", "고령", "복지", "커버리지", "지니")):
        metrics = context.get("social_impact", [])
        details = []
        for metric in metrics:
            details.append(f"{metric['label']}: {metric['value']} ({metric.get('reason', '')})")
        return "사회 변화 지표의 계산 근거입니다.\n" + "\n".join(details)
    if any(word in compact for word in ("이유", "왜", "원인", "어째서")):
        return (
            f"이 결과는 선택한 세율, 분배 방식, 계층 수, 경제 시나리오를 복합적으로 계산한 것입니다. "
            f"2035년 지니계수는 {gini:.3f}이고, 세수는 약 {tax:.1f}억원으로 예상됩니다. "
            f"현재 조건은 세율 {tax_percent}%의 {mode_name}, {scenario_name} 시나리오입니다. "
            f"예측된 경제 전환점은 '{future_event.get('year', '-')}년: {future_event.get('event', '-')}'입니다."
        )
    return (
        "죄송합니다. 제가 현재 시뮬레이션 데이터로는 그 질문에 확실하게 답하기 어렵습니다. "
        "2030년 예측, 세율 변화, 분배 방식, 인구수, 사회 변화 지표 같은 "
        "이 화면의 정책 결과에 관해 다시 질문해 주시면 근거를 함께 설명해 드릴게요."
    )


@app.route('/gemini_chat', methods=['POST'])
def gemini_chat():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    data = request.get_json() or {}
    question = str(data.get("question", "")).strip()
    context = data.get("context", {})
    history = data.get("history", [])
    if not question:
        return jsonify({"status": "error", "message": "질문을 입력해 주세요."}), 400
    if len(question) > 2000:
        return jsonify({"status": "error", "message": "질문은 2,000자 이내로 입력해 주세요."}), 400
    if not api_key:
        return jsonify({
            "status": "success",
            "answer": make_local_ai_answer(question, context),
            "engine": "local-policy-ai",
        })

    prompt = (
        "너는 한국어 경제 정책 분석 보조자다. 아래 시뮬레이션 결과를 근거로 사용자의 질문에 "
        "쉽고 구체적으로 답하되, 시뮬레이션 가정과 실제 정책의 차이를 명확히 밝혀라.\n"
        "현재 화면 데이터에 없는 정보는 추측하지 말고, 답할 수 없으면 "
        "'죄송합니다. 이 정보는 제가 확실하게 답하기 어렵습니다.'라고 솔직하게 말하라.\n"
        f"시뮬레이션 맥락:\n{json.dumps(context, ensure_ascii=False)}\n"
        "최근 대화:\n" + "\n".join(
            f"{'사용자' if item.get('role') == 'user' else 'AI'}: {item.get('content', '')}"
            for item in history[-6:]
            if isinstance(item, dict)
        ) + "\n"
        f"사용자 질문:\n{question}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent?key=" + api_key
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 800},
    }).encode("utf-8")

    req = urllib_request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        return jsonify({"status": "success", "answer": answer})
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return jsonify({"status": "error", "message": f"Gemini API 요청에 실패했습니다. ({error.code})", "detail": detail[:500]}), 502
    except (URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        return jsonify({"status": "error", "message": "Gemini 응답을 가져오지 못했습니다. 잠시 후 다시 시도해 주세요."}), 502


@app.route('/simulate', methods=['POST'])
def simulate():
    try:
        data = request.get_json() or {}
        initial_profit = float(data.get('initial_profit', 1000))
        stages = int(data.get('stages', 5))
        tax_percent = float(data.get('tax_rate', 25))
        population = max(10_000_000, float(data.get('population', DEFAULT_POPULATION)))
        scenario = data.get('scenario', 'steady')
        distribution_mode = data.get('distribution_mode', 'basic')
        if scenario not in SCENARIOS:
            scenario = 'steady'
        if distribution_mode not in MODES:
            distribution_mode = 'basic'

        result = run_simulation(initial_profit, stages, tax_percent / 100.0, population, scenario, distribution_mode)
        actual_short = get_grade(result["gini"][SHORT_YEAR_INDEX])
        actual_long = get_grade(result["gini"][LONG_YEAR_INDEX])
        ai_report = build_ai_report(min(55, max(8, tax_percent)), distribution_mode, stages, scenario,
                                    actual_short, actual_long)

        return jsonify({
            "status": "success",
            **result,
            "population": int(population),
            "initial_profit": initial_profit,
            "tax_rate": tax_percent,
            "stages": stages,
            "scenario": scenario,
            "distribution_mode": distribution_mode,
            "ai_report": ai_report,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# 의사결정나무 전체 규칙을 글로 보여 주는 주소 (발표·검증용)
@app.route('/ai_tree')
def ai_tree():
    result = {"training_size": AI_DATA_SIZE}
    for key, label in (("short", "단기_2030"), ("long", "장기_2035")):
        result[label] = {
            "accuracy": round(AI_MODELS[key]["accuracy"] * 100, 1),
            "rules": export_text(AI_MODELS[key]["model"], feature_names=FEATURE_NAMES),
        }
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True, port=5001)
