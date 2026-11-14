let economyChart = null;

document.addEventListener('DOMContentLoaded', () => {
    const profitInput = document.getElementById('initial_profit');
    const profitSlider = document.getElementById('profit_slider');
    const taxRateInput = document.getElementById('tax_rate');
    const taxRateSlider = document.getElementById('tax_rate_slider');
    const populationInput = document.getElementById('population');
    const runBtn = document.getElementById('run_btn');

    if (!profitInput || !runBtn) {
        console.error("AI 시뮬레이터 에러: 필수 UI 요소를 화면(HTML)에서 찾을 수 없습니다.");
        return;
    }

    const keepRunButtonVisible = () => {
        runBtn.hidden = false;
        runBtn.disabled = false;
        runBtn.style.display = 'block';
        runBtn.style.visibility = 'visible';
        runBtn.style.opacity = '1';
        runBtn.style.pointerEvents = 'auto';
    };

    const syncProfitControls = (value) => {
        const numericValue = Number(value);
        if (Number.isNaN(numericValue)) return;
        const clampedValue = Math.min(Math.max(numericValue, 500), 1000000);
        profitInput.value = clampedValue;
        if (profitSlider) profitSlider.value = clampedValue;
    };

    const syncTaxControls = (value) => {
        const numericValue = Number(value);
        if (Number.isNaN(numericValue)) return;
        const clampedValue = Math.min(Math.max(numericValue, 5), 60);
        if (taxRateInput) taxRateInput.value = clampedValue;
        if (taxRateSlider) taxRateSlider.value = clampedValue;
    };

    if (profitSlider) {
        profitInput.addEventListener('input', (event) => syncProfitControls(event.target.value));
        profitSlider.addEventListener('input', (event) => syncProfitControls(event.target.value));
    }

    if (taxRateInput && taxRateSlider) {
        taxRateInput.addEventListener('input', (event) => syncTaxControls(event.target.value));
        taxRateSlider.addEventListener('input', (event) => syncTaxControls(event.target.value));
    }

    if (populationInput) {
        populationInput.addEventListener('input', (event) => {
            const population = Number(event.target.value);
            if (!Number.isNaN(population)) {
                populationInput.value = Math.min(Math.max(population, 10000000), 100000000);
            }
        });
    }

    async function runSimulation() {
        let initialProfit = parseFloat(profitInput.value);

        if (Number.isNaN(initialProfit) || initialProfit < 500) {
            alert('최소 500억원 이상의 숫자를 입력해 주세요.');
            profitInput.value = 1000;
            initialProfit = 1000;
        }

        const checkedRadio = document.querySelector('input[name="stages"]:checked');
        const selectedStage = checkedRadio ? checkedRadio.value : 5;
        const selectedScenario = document.querySelector('input[name="scenario"]:checked')?.value || 'steady';
        const selectedDistribution = document.querySelector('input[name="distribution_mode"]:checked')?.value || 'basic';
        const selectedTaxRate = Number((taxRateInput || {}).value || 25);
        const selectedPopulation = Number((populationInput || {}).value || 51744000);

        keepRunButtonVisible();

        try {
            const response = await fetch('/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    initial_profit: initialProfit,
                    stages: selectedStage,
                    tax_rate: selectedTaxRate,
                    population: selectedPopulation,
                    scenario: selectedScenario,
                    distribution_mode: selectedDistribution,
                })
            });

            if (!response.ok) {
                throw new Error('서버와 데이터를 주고받는 데 실패했습니다.');
            }

            const data = await response.json();

            if (data.status === 'error') {
                alert('연산 오류 발생: ' + data.message);
                return;
            }

            const resRateEl = document.getElementById('res_rate');
            const resTaxEl = document.getElementById('res_tax');
            if (resRateEl) resRateEl.textContent = data.last_rate;
            if (resTaxEl) resTaxEl.textContent = Number(data.last_tax).toLocaleString();

            const listContainer = document.getElementById('distribution_list');
            if (listContainer) {
                listContainer.innerHTML = '';
                data.stages_data.forEach((item) => {
                    const itemDiv = document.createElement('div');
                    itemDiv.className = 'report-item';
                    itemDiv.innerHTML = `
                        <div class="name-info">
                            <span class="name">${item.stage_name}</span>
                            <span class="tag">할당 비중 ${item.ratio}%</span>
                        </div>
                        <span class="price">연 ${item.amount.toLocaleString()}만원</span>
                    `;
                    listContainer.appendChild(itemDiv);
                });
            }

            const socialList = document.getElementById('social_impact_list');
            if (socialList && Array.isArray(data.social_impact)) {
                socialList.innerHTML = data.social_impact.map((metric) => `
                    <div class="impact-item">
                        <span class="impact-label">${metric.label}</span>
                        <div class="impact-value">${metric.value}</div>
                        <span class="impact-note">${metric.note}</span>
                    </div>
                `).join('');
            }

            const canvas = document.getElementById('economyChart');
            if (!canvas) {
                console.error("AI 시뮬레이터 에러: 'economyChart' ID를 가진 캔버스를 찾을 수 없습니다.");
                return;
            }

            if (typeof Chart === 'undefined') {
                alert('시각화 라이브러리(Chart.js) 로딩이 지연되고 있습니다. 잠시 후 다시 실행해 주세요.');
                return;
            }

            const ctx = canvas.getContext('2d');
            if (!ctx) {
                console.error('AI 시뮬레이터 에러: 2D 캔버스 컨텍스트를 초기화할 수 없습니다.');
                return;
            }

            if (economyChart) {
                economyChart.destroy();
            }

            economyChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.years,
                    datasets: [
                        {
                            label: '확보 세수 (억원)',
                            data: data.tax,
                            backgroundColor: '#3182f6',
                            borderRadius: 6,
                            yAxisID: 'y-tax'
                        },
                        {
                            label: '빈부격차 (지니계수)',
                            data: data.gini,
                            type: 'line',
                            borderColor: '#f59e0b',
                            borderWidth: 3,
                            pointBackgroundColor: '#f59e0b',
                            tension: 0.2,
                            yAxisID: 'y-gini'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        'y-tax': {
                            type: 'linear',
                            position: 'left',
                            grid: { color: '#f1f5f9' },
                            ticks: { color: '#64748b' }
                        },
                        'y-gini': {
                            type: 'linear',
                            position: 'right',
                            min: 0.2,
                            max: 0.6,
                            grid: { drawOnChartArea: false },
                            ticks: { color: '#64748b' }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#64748b' }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: { boxWidth: 12 }
                        }
                    }
                }
            });
        } catch (error) {
            console.error('시뮬레이터 네트워크 오류:', error);
            alert('시뮬레이션 실행 중 네트워크 혹은 비동기 데이터 에러가 발생했습니다.');
        }
    }

    document.querySelectorAll('input[name="stages"], input[name="scenario"], input[name="distribution_mode"]').forEach((input) => {
        input.addEventListener('change', () => {
            keepRunButtonVisible();
        });
    });

    keepRunButtonVisible();
    runBtn.addEventListener('click', runSimulation);
    runSimulation();
});
