let economyChart = null;
let currentSimulationContext = null;
let aiChatHistory = [];
let aiSimulationSessions = [];
let activeAiSessionId = null;

const aiReportModal = () => document.getElementById('ai_report_modal');

function clearBaseAndPopupChat() {
    const popupMessages = document.getElementById('gemini_chat_messages');
    const baseMessages = document.getElementById('base_ai_messages');
    if (popupMessages) popupMessages.innerHTML = '';
    if (baseMessages) baseMessages.innerHTML = '';
}

function createAiSimulationSession(data) {
    const modeNames = { equal: '동일분배', basic: '기본소득형', custom: '맞춤형', targeted: '집중지원' };
    const shortGrade = data.ai_report?.short_term?.predicted_grade || '-';
    const session = {
        id: `ai-session-${Date.now()}-${aiSimulationSessions.length + 1}`,
        label: `시뮬레이션 ${aiSimulationSessions.length + 1}`,
        summary: `세율 ${data.tax_rate}% · ${modeNames[data.distribution_mode] || data.distribution_mode} · 2030 ${shortGrade}`,
        context: data,
        messages: [],
        questionCount: 0,
    };
    aiSimulationSessions.unshift(session);
    activeAiSessionId = session.id;
    aiChatHistory = session.messages;
    currentSimulationContext = data;
    clearBaseAndPopupChat();
    renderAiHistoryLists();
}

function saveAiSessionMessage(role, content) {
    const session = aiSimulationSessions.find((item) => item.id === activeAiSessionId);
    if (!session) return;
    session.messages.push({ role, content });
    aiChatHistory = session.messages;
    if (role === 'user') session.questionCount += 1;
    session.summary = `${session.summary.split(' · 질문')[0]} · 질문 ${session.questionCount}개`;
    renderAiHistoryLists();
}

function renderChatHistory(containerId, messages) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    messages.forEach((message) => {
        const bubble = document.createElement('div');
        bubble.className = `gemini-message ${message.role === 'user' ? 'gemini-user' : 'gemini-assistant'}`;
        bubble.textContent = message.content;
        container.appendChild(bubble);
    });
    container.scrollTop = container.scrollHeight;
}

function selectAiSession(sessionId) {
    const session = aiSimulationSessions.find((item) => item.id === sessionId);
    if (!session) return;
    activeAiSessionId = session.id;
    aiChatHistory = session.messages;
    currentSimulationContext = session.context;
    renderChatHistory('gemini_chat_messages', session.messages);
    renderChatHistory('base_ai_messages', session.messages);
    renderAiHistoryLists();
}

function renderAiHistoryLists() {
    const targets = ['popup_ai_history_list', 'base_ai_history_list'];
    targets.forEach((targetId) => {
        const list = document.getElementById(targetId);
        if (!list) return;
        list.innerHTML = '';
        aiSimulationSessions.forEach((session) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `ai-history-item${session.id === activeAiSessionId ? ' active' : ''}`;
            button.innerHTML = `<strong>${escapeHtml(session.label)}</strong><span>${escapeHtml(session.summary)}</span>`;
            button.addEventListener('click', () => selectAiSession(session.id));
            list.appendChild(button);
        });
        if (!aiSimulationSessions.length) {
            list.innerHTML = '<p class="ai-history-empty">아직 질문 기록이 없습니다.</p>';
        }
    });
}

function openAiReportModal() {
    const modal = aiReportModal();
    const loading = document.getElementById('ai_report_loading');
    const content = document.getElementById('ai_report_content');
    const chatMessages = document.getElementById('gemini_chat_messages');
    const chatInput = document.getElementById('gemini_chat_input');
    if (!modal) return;
    if (loading) loading.hidden = false;
    if (content) content.hidden = true;
    if (chatMessages) chatMessages.innerHTML = '';
    aiChatHistory = [];
    if (chatInput) {
        chatInput.value = '';
        chatInput.disabled = false;
    }
    const baseMessages = document.getElementById('base_ai_messages');
    const baseInput = document.getElementById('base_ai_input');
    if (baseMessages) baseMessages.innerHTML = '';
    if (baseInput) {
        baseInput.value = '';
        baseInput.disabled = false;
    }
    modal.hidden = false;
}

function closeAiReportModal() {
    const modal = aiReportModal();
    if (modal) modal.hidden = true;
}

async function askBaseAi(question) {
    const messages = document.getElementById('base_ai_messages');
    const input = document.getElementById('base_ai_input');
    if (!messages || !input) return;

    if (!currentSimulationContext) {
        const notice = document.createElement('div');
        notice.className = 'gemini-message gemini-assistant';
        notice.textContent = '먼저 시뮬레이션 실행하기를 눌러 정책 결과를 만든 뒤 질문해 주세요.';
        messages.appendChild(notice);
        messages.scrollTop = messages.scrollHeight;
        return;
    }

    const userMessage = document.createElement('div');
    userMessage.className = 'gemini-message gemini-user';
    userMessage.textContent = question;
    messages.appendChild(userMessage);

    const assistantMessage = document.createElement('div');
    assistantMessage.className = 'gemini-message gemini-assistant';
    assistantMessage.textContent = '분석 중...';
    messages.appendChild(assistantMessage);
    messages.scrollTop = messages.scrollHeight;
    input.value = '';
    input.disabled = true;
    saveAiSessionMessage('user', question);

    try {
        const response = await fetch('/gemini_chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question,
                context: currentSimulationContext,
                history: aiChatHistory.slice(-6),
            }),
        });
        const data = await response.json();
        assistantMessage.textContent = data.status === 'success'
            ? data.answer
            : data.message || 'AI 응답을 가져오지 못했습니다.';
        if (data.status === 'success') {
            saveAiSessionMessage('assistant', data.answer);
        }
    } catch (error) {
        console.error('AI 도우미 요청 오류:', error);
        assistantMessage.textContent = 'AI 서버에 연결하지 못했습니다.';
    } finally {
        input.disabled = false;
        input.focus();
        messages.scrollTop = messages.scrollHeight;
    }
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

async function askGemini(question) {
    const messages = document.getElementById('gemini_chat_messages');
    const input = document.getElementById('gemini_chat_input');
    if (!messages || !input) return;

    const userMessage = document.createElement('div');
    userMessage.className = 'gemini-message gemini-user';
    userMessage.textContent = question;
    messages.appendChild(userMessage);
    saveAiSessionMessage('user', question);

    const assistantMessage = document.createElement('div');
    assistantMessage.className = 'gemini-message gemini-assistant';
    assistantMessage.textContent = 'AI가 시뮬레이션 결과를 분석 중입니다...';
    messages.appendChild(assistantMessage);
    messages.scrollTop = messages.scrollHeight;
    input.value = '';
    input.disabled = true;

    try {
        const response = await fetch('/gemini_chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question,
                context: currentSimulationContext,
                history: aiChatHistory.slice(-6),
            }),
        });
        const data = await response.json();
        assistantMessage.textContent = data.status === 'success'
            ? data.answer
            : data.message || 'AI 응답을 가져오지 못했습니다.';
        if (data.status === 'success') {
            saveAiSessionMessage('assistant', data.answer);
        }
    } catch (error) {
        console.error('Gemini 요청 오류:', error);
        assistantMessage.textContent = 'Gemini 서버에 연결하지 못했습니다.';
    } finally {
        input.disabled = false;
        input.focus();
        messages.scrollTop = messages.scrollHeight;
    }
}

function renderAiReportModal(report) {
    if (!report) return;
    const loading = document.getElementById('ai_report_loading');
    const content = document.getElementById('ai_report_content');
    if (loading) loading.hidden = true;
    if (!content) return;

    const shortTerm = report.short_term || {};
    const futureEvent = report.future_event || {};
    const factors = (report.short_term?.important_factors || []).slice(0, 3)
        .map((item) => `${item.factor} ${item.percent}%`).join(', ');
    const suggestions = (report.suggestions || []).map((item) => `<li>${item}</li>`).join('');

    content.innerHTML = `
        <div class="report-summary">${report.summary}</div>
        <div class="report-grid">
            <div class="report-box">
                <h3>2030년 예측: ${shortTerm.predicted_grade || '-'}</h3>
                <p>예측 신뢰도 ${shortTerm.confidence || 0}%</p>
                <p>의사결정나무 정확도 ${shortTerm.model_accuracy || 0}%</p>
                <p>주요 영향 요인: ${factors || '-'}</p>
            </div>
            <div class="report-box event-box">
                <h3>${futureEvent.year || '예측 연도 미확정'}년 경제 전환 예측</h3>
                <p>${futureEvent.event || '-'}</p>
                <p>${futureEvent.reason || ''}</p>
            </div>
        </div>
        <div class="report-grid">
            <div class="report-box">
                <h3>장기 예측(2035년)</h3>
                <p>${report.long_term?.predicted_grade || '-'} / 신뢰도 ${report.long_term?.confidence || 0}%</p>
                <ul>${suggestions || '<li>별도 개선안이 뚜렷하지 않습니다.</li>'}</ul>
            </div>
            <div class="report-box">
                <h3>AI 분석 근거</h3>
                <p>${(shortTerm.decision_path || []).join(' → ') || '분석 경로 없음'}</p>
            </div>
        </div>
        <p class="report-notice">${report.notice || ''}</p>
    `;
    content.hidden = false;
}

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
        if (profitSlider) profitSlider.value = clampedValue;
    };

    const clearProfitError = () => {
        profitInput.classList.remove('profit-input-error');
        profitInput.setAttribute('aria-invalid', 'false');
        const profitError = document.getElementById('profit_error');
        if (profitError) profitError.hidden = true;
    };

    const showProfitError = () => {
        profitInput.classList.add('profit-input-error');
        profitInput.setAttribute('aria-invalid', 'true');
        const profitError = document.getElementById('profit_error');
        if (profitError) profitError.hidden = false;
    };

    const syncTaxControls = (value) => {
        const numericValue = Number(value);
        if (Number.isNaN(numericValue)) return;
        const clampedValue = Math.min(Math.max(numericValue, 5), 60);
        if (taxRateInput) taxRateInput.value = clampedValue;
        if (taxRateSlider) taxRateSlider.value = clampedValue;
    };

    if (profitSlider) {
        profitInput.addEventListener('input', (event) => {
            const numericValue = Number(event.target.value);
            if (!Number.isNaN(numericValue) && numericValue >= 500) {
                clearProfitError();
            }
            if (!Number.isNaN(numericValue) && numericValue >= 500) {
                syncProfitControls(numericValue);
            }
        });
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
        const initialProfit = parseFloat(profitInput.value);

        if (Number.isNaN(initialProfit) || initialProfit < 500) {
            showProfitError();
            profitInput.focus();
            return;
        }
        clearProfitError();

        const checkedRadio = document.querySelector('input[name="stages"]:checked');
        const selectedStage = checkedRadio ? checkedRadio.value : 5;
        const selectedScenario = document.querySelector('input[name="scenario"]:checked')?.value || 'steady';
        const selectedDistribution = document.querySelector('input[name="distribution_mode"]:checked')?.value || 'basic';
        const selectedTaxRate = Number((taxRateInput || {}).value || 25);
        const selectedPopulation = Number((populationInput || {}).value || 51117378);

        keepRunButtonVisible();
        openAiReportModal();

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
                closeAiReportModal();
                return;
            }

            createAiSimulationSession(data);
            renderAiReportModal(data.ai_report);

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
                    <div class="impact-item" data-tooltip="${escapeHtml(metric.reason || '이 지표의 계산 근거입니다.')}">
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
                            order: 2,
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
                            order: 0,
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
            closeAiReportModal();
        }
    }

    document.querySelectorAll('input[name="stages"], input[name="scenario"], input[name="distribution_mode"]').forEach((input) => {
        input.addEventListener('change', () => {
            keepRunButtonVisible();
        });
    });

    keepRunButtonVisible();
    runBtn.addEventListener('click', runSimulation);
    document.getElementById('close_ai_report')?.addEventListener('click', closeAiReportModal);
    aiReportModal()?.addEventListener('click', (event) => {
        if (event.target === aiReportModal()) closeAiReportModal();
    });
    document.getElementById('gemini_chat_form')?.addEventListener('submit', (event) => {
        event.preventDefault();
        const input = document.getElementById('gemini_chat_input');
        const question = input?.value.trim();
        if (question) askGemini(question);
    });
    document.querySelectorAll('.gemini-question-presets button').forEach((button) => {
        button.addEventListener('click', () => {
            const question = button.dataset.question;
            if (question) askGemini(question);
        });
    });
    const baseToggle = document.getElementById('base_ai_toggle');
    const basePanel = document.getElementById('base_ai_panel');
    baseToggle?.addEventListener('click', () => {
        if (!basePanel) return;
        const willOpen = basePanel.hidden;
        basePanel.hidden = !willOpen;
        baseToggle.setAttribute('aria-expanded', String(willOpen));
        document.getElementById('base_ai_toggle_icon').textContent = willOpen ? '－' : '＋';
        if (willOpen) document.getElementById('base_ai_input')?.focus();
    });
    document.getElementById('base_ai_form')?.addEventListener('submit', (event) => {
        event.preventDefault();
        const input = document.getElementById('base_ai_input');
        const question = input?.value.trim();
        if (question) askBaseAi(question);
    });
    document.querySelectorAll('.base-ai-presets button').forEach((button) => {
        button.addEventListener('click', () => {
            const question = button.dataset.question;
            if (question) askBaseAi(question);
        });
    });
    document.getElementById('popup_ai_history_toggle')?.addEventListener('click', (event) => {
        const sidebar = document.getElementById('popup_ai_history_sidebar');
        if (!sidebar) return;
        sidebar.hidden = !sidebar.hidden;
        event.currentTarget.setAttribute('aria-expanded', String(!sidebar.hidden));
        renderAiHistoryLists();
    });
    document.getElementById('base_ai_history_toggle')?.addEventListener('click', (event) => {
        const sidebar = document.getElementById('base_ai_history_sidebar');
        if (!sidebar) return;
        sidebar.hidden = !sidebar.hidden;
        event.currentTarget.setAttribute('aria-expanded', String(!sidebar.hidden));
        renderAiHistoryLists();
    });
});
