let csrfToken = '';
let practiceQuestions = [];
let practiceDraftUpdatedAt = '';

function practiceEscape(value) {
    const text = value === null || value === undefined ? '' : String(value);
    return text.replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
}

async function practiceApi(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
    const response = await fetch(url, { ...options, headers, credentials: 'same-origin' });
    const data = await response.json();
    if (!data.success) throw new Error(data.message || '操作失败');
    return data;
}

async function loadCsrfToken() {
    const data = await practiceApi('/api/csrf-token');
    csrfToken = data.csrf_token || '';
}

function answerLabel(question, value) {
    if (!value) return '-';
    const options = Array.isArray(question.options) ? question.options : [];
    return String(value).split(',').filter(Boolean).map(key => {
        const option = options.find(candidate => candidate.key === key);
        return option ? `${option.key}. ${option.text}` : key;
    }).join('，');
}

function renderDailyStatus(status) {
    const target = document.getElementById('practiceDailyStatus');
    if (!target) return;
    if (!status || status.session_count === 0) {
        target.textContent = '今日未打卡：完成30题，正确率达到80%即合格。';
        return;
    }
    const percent = Math.round((status.best_accuracy || 0) * 100);
    target.textContent = status.passed
        ? `今日已合格：最高正确率 ${percent}%，已做 ${status.answered_count} 题。`
        : `今日未达标：最高正确率 ${percent}%，已做 ${status.answered_count} 题，请继续练习。`;
}

async function loadDailyStatus() {
    const data = await practiceApi('/api/exam/practice/daily-status');
    renderDailyStatus(data.data || {});
}

function renderQuestions(savedAnswers = {}, updatedAt = '') {
    const root = document.getElementById('practiceRoot');
    const questionCards = practiceQuestions.map((question, index) => {
        const inputType = question.question_type === 'multiple_choice' ? 'checkbox' : 'radio';
        const selectedValues = new Set(
            String(savedAnswers[String(question.id)] || '').split(',').filter(Boolean)
        );
        const options = (question.options || []).map(option => `
            <label>
                <input type="${inputType}" name="q_${practiceEscape(question.id)}" value="${practiceEscape(option.key)}" ${selectedValues.has(String(option.key)) ? 'checked' : ''}>
                <span>${practiceEscape(option.key)}. ${practiceEscape(option.text)}</span>
            </label>
        `).join('');
        return `
            <article class="practice-card" data-question-id="${practiceEscape(question.id)}">
                <strong>${index + 1}. ${practiceEscape(question.stem)}</strong>
                <div class="practice-meta">${practiceEscape(question.paper_title || '')}</div>
                <div class="practice-options">${options}</div>
            </article>
        `;
    }).join('');
    root.innerHTML = `
        <form id="practiceForm" onsubmit="submitPractice(event)">
            <div class="practice-card">
                <strong>本次共 ${practiceQuestions.length} 题</strong>
                <div class="practice-meta">正确率达到 80% 视为今日合格打卡，未达标需要继续练习。</div>
                <div class="practice-meta" id="practiceDraftStatus">${updatedAt ? `已恢复暂存：${practiceEscape(updatedAt)}` : ''}</div>
            </div>
            ${questionCards}
            <div class="practice-actions">
                <button class="btn btn-primary" type="submit">提交打卡</button>
                <button class="btn btn-secondary" type="button" onclick="savePracticeDraft(event)">暂存</button>
                <button class="btn btn-secondary" type="button" onclick="loadPractice({ clearDraft: true })">换一组题</button>
            </div>
        </form>
    `;
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

async function loadPractice(options = {}) {
    const root = document.getElementById('practiceRoot');
    root.innerHTML = '<div class="practice-card">正在加载30道练习题...</div>';
    if (options.clearDraft) {
        await practiceApi('/api/exam/practice/draft', { method: 'DELETE' });
    }
    const data = await practiceApi('/api/exam/practice/random?limit=30');
    practiceQuestions = data.data || [];
    practiceDraftUpdatedAt = '';
    renderQuestions();
}

async function restorePracticeDraft() {
    const data = await practiceApi('/api/exam/practice/draft');
    const draft = data.data;
    if (!draft || !Array.isArray(draft.questions) || draft.questions.length === 0) {
        return false;
    }
    practiceQuestions = draft.questions;
    practiceDraftUpdatedAt = draft.updated_at || '';
    renderQuestions(draft.answers || {}, practiceDraftUpdatedAt);
    return true;
}

function collectAnswers() {
    const answers = {};
    for (const question of practiceQuestions) {
        const checked = [...document.querySelectorAll(`[name="q_${question.id}"]:checked`)]
            .map(input => input.value);
        answers[String(question.id)] = checked.join(',');
    }
    return answers;
}

async function submitPractice(event) {
    event.preventDefault();
    const button = event.target.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    try {
        const data = await practiceApi('/api/exam/practice/submit', {
            method: 'POST',
            body: JSON.stringify({ answers: collectAnswers() })
        });
        renderResult(data.data || {});
        await loadDailyStatus();
    } catch (error) {
        if (button) button.disabled = false;
        alert(error.message || '提交失败');
    }
}

async function savePracticeDraft(event) {
    if (!practiceQuestions.length) return;
    const button = event && event.target ? event.target : null;
    if (button) button.disabled = true;
    try {
        const data = await practiceApi('/api/exam/practice/draft', {
            method: 'PUT',
            body: JSON.stringify({
                question_ids: practiceQuestions.map(question => question.id),
                answers: collectAnswers()
            })
        });
        practiceDraftUpdatedAt = (data.data && data.data.updated_at) || '';
        const status = document.getElementById('practiceDraftStatus');
        if (status) {
            status.textContent = practiceDraftUpdatedAt ? `已暂存：${practiceDraftUpdatedAt}` : '已暂存';
        }
    } catch (error) {
        alert(error.message || '暂存失败');
    } finally {
        if (button) button.disabled = false;
    }
}

function renderResult(result) {
    const root = document.getElementById('practiceRoot');
    const percent = Math.round((result.accuracy || 0) * 100);
    const statusClass = result.passed ? 'daily-checkin-passed' : 'daily-checkin-failed';
    const statusText = result.passed
        ? `本次正确率 ${percent}%，今日打卡合格。`
        : `本次正确率 ${percent}%，未达到80%，请继续练习。`;
    const rows = (result.items || []).map((item, index) => `
        <article class="practice-card ${item.is_correct ? 'practice-correct' : 'practice-wrong'}">
            <strong>${index + 1}. ${practiceEscape(item.stem)}</strong>
            <p>你的答案：${practiceEscape(answerLabel(item, item.answer_text))}</p>
            <p>正确答案：${practiceEscape(answerLabel(item, item.correct_answer))}</p>
            <p>解析：${practiceEscape(item.reference_answer || `题库暂未配置详细解析，正确答案为：${answerLabel(item, item.correct_answer)}`)}</p>
            <p>结果：${item.is_correct ? '正确' : '错误'}</p>
        </article>
    `).join('');
    root.innerHTML = `
        <section class="practice-card ${statusClass}">
            <h2>${statusText}</h2>
            <div class="practice-meta">本次 ${result.total_count || 0} 题，正确 ${result.correct_count || 0} 题。</div>
            <div class="practice-actions">
                <button class="btn btn-primary" type="button" onclick="loadPractice()">继续练习</button>
                <button class="btn btn-secondary" type="button" onclick="returnToExamCenter()">返回考试中心</button>
            </div>
        </section>
        ${rows}
    `;
}

function returnToExamCenter() {
    window.location.href = '/#exam';
}

document.addEventListener('DOMContentLoaded', async () => {
    try {
        await loadCsrfToken();
        await loadDailyStatus();
        const restored = await restorePracticeDraft();
        if (!restored) await loadPractice();
    } catch (error) {
        document.getElementById('practiceRoot').innerHTML = `
            <div class="practice-card daily-checkin-failed">
                ${practiceEscape(error.message || '练习页加载失败，请重新登录后再试。')}
            </div>
        `;
    }
});
