from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
DEFAULT_POPULATION = 51_744_000


def get_scenario_config(name):
    config = {
        "steady": {"growth": 1.0, "aging": 1.0, "stability": 1.0},
        "innovation": {"growth": 1.25, "aging": 0.9, "stability": 1.08},
        "aging": {"growth": 0.88, "aging": 1.4, "stability": 0.92},
        "crisis": {"growth": 0.72, "aging": 1.2, "stability": 0.8},
    }
    return config.get(name, config["steady"])


def get_distribution_weights(stages, mode):
    if mode == "equal":
        return [1.0 for _ in range(stages)]
    if mode == "basic":
        return [max(0.7, float(stages - i)) for i in range(stages)]
    if mode == "custom":
        return [max(0.7, float(1.35 + (stages - i) * 0.75)) for i in range(stages)]
    if mode == "targeted":
        return [max(0.7, float(2.2 + (stages - i) * 0.9)) for i in range(stages)]
    return [max(0.7, float(stages - i)) for i in range(stages)]


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/simulate', methods=['POST'])
def simulate():
    try:
        data = request.get_json() or {}
        initial_profit = float(data.get('initial_profit', 1000))
        stages = int(data.get('stages', 5))
        tax_rate = float(data.get('tax_rate', 25)) / 100.0
        population = max(10_000_000, float(data.get('population', DEFAULT_POPULATION)))
        scenario = data.get('scenario', 'steady')
        distribution_mode = data.get('distribution_mode', 'basic')

        scenario_cfg = get_scenario_config(scenario)
        weights = get_distribution_weights(stages, distribution_mode)
        total_weight = sum(weights)
        distribution_ratios = [w / total_weight for w in weights]

        years = [str(year) for year in range(2026, 2036)]
        chart_profit, chart_tax, chart_gini = [], [], []

        current_profit = initial_profit
        base_gini = 0.42
        tax_rate = min(0.55, max(0.08, tax_rate))

        for idx, _year in enumerate(years):
            if idx > 0:
                current_profit *= (1.10 + (scenario_cfg["growth"] - 1.0) * 0.20)
                base_gini = min(0.62, base_gini + 0.012 * scenario_cfg["aging"])

            effective_rate = min(0.50, max(0.08, tax_rate * (1.0 + (scenario_cfg["stability"] - 1.0) * 0.25)))
            total_tax = current_profit * effective_rate

            gini_reduction = (total_tax / max(initial_profit, 1.0)) * 0.10 * (float(stages) / 5.0)
            simulated_gini = max(0.27, base_gini - gini_reduction)

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
        welfare_coverage = max(35, min(95, 42 + (effective_rate * 50) + (scenario_cfg["stability"] * 10)))
        aging_ratio = max(12, min(38, 18 + (scenario_cfg["aging"] - 1.0) * 16))

        social_impact = [
            {"label": "소득 불균형", "value": f"{final_gini:.2f}", "note": "지니계수"},
            {"label": "사회 안정도", "value": f"{social_stability:.0f}/100", "note": "국민 체감 지수"},
            {"label": "고령화 부담", "value": f"{aging_ratio:.1f}%", "note": "노인 부양비"},
            {"label": "복지 커버리지", "value": f"{welfare_coverage:.0f}%", "note": "기본소득/복지"},
        ]

        return jsonify({
            "status": "success",
            "years": years,
            "profit": chart_profit,
            "tax": chart_tax,
            "gini": chart_gini,
            "stages_data": stage_results,
            "last_tax": round(chart_tax[-1], 1),
            "last_rate": round(effective_rate * 100, 1),
            "population": int(population),
            "scenario": scenario,
            "distribution_mode": distribution_mode,
            "social_impact": social_impact,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == '__main__':
    app.run(debug=True, port=5001)
