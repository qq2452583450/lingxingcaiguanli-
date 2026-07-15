let examSummary = null;
let examCurrentTab = 'practice';
let examActiveAttempt = null;
let examCheckinFilter = 'all';
let examCheckinRecords = [];
let examAttendanceMonth = '';

const EXAM_TAKER_ROLES = ['材料员', '材料审批负责人', '基地负责人'];
const EXAM_MANAGER_ROLES = ['材料审批负责人', '系统管理员'];
const EXAM_OBJECTIVE_TYPES = ['single_choice', 'multiple_choice', 'true_false'];

function examUser(user) {
    return user || currentUser || JSON.parse(sessionStorage.getItem('currentUser') || '{}');
}

function canTakeExam(user = currentUser) {
    return EXAM_TAKER_ROLES.includes(examUser(user).role_name);
}

function canUseExamCenter(user = currentUser) {
    return canTakeExam(user) || canManageExam(user);
}

function canManageExam(user = currentUser) {
    return EXAM_MANAGER_ROLES.includes(examUser(user).role_name);
}

function examEscape(value) {
    const text = value === null || value === undefined ? '' : String(value);
    if (typeof escapeHtml === 'function') return escapeHtml(text);
    return text.replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
}

function examStatusText(status) {
    const map = {
        in_progress: '进行中',
        pending_review: '待阅卷',
        completed: '已完成'
    };
    return map[status] || status || '-';
}

function examScore(value) {
    if (value === null || value === undefined || value === '') return '-';
    const num = Number(value);
    return Number.isFinite(num) ? num.toFixed(1).replace(/\.0$/, '') : examEscape(value);
}

function examDate(value) {
    return value ? String(value).slice(0, 16) : '-';
}

function examNotify(message, type = 'info') {
    if (typeof showToast === 'function') showToast(message, type);
}

function examRefreshIcons() {
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function examContent() {
    return document.getElementById('examContent');
}

async function examJson(url, options = {}) {
    const res = await api(url, options);
    const data = await res.json();
    if (!data.success) {
        throw new Error(data.message || '操作失败');
    }
    return data;
}

function examLoading(message = '加载中...') {
    const content = examContent();
    if (content) content.innerHTML = `<div class="exam-panel"><div class="loading">${message}</div></div>`;
}

function examError(message) {
    const content = examContent();
    if (content) content.innerHTML = `<div class="exam-panel"><div class="error-message">${examEscape(message)}</div></div>`;
}

async function loadExamCenter() {
    if (!canUseExamCenter(currentUser)) {
        examError('当前账号无权访问考试中心');
        return;
    }

    try {
        const data = await examJson('/api/exam/summary');
        examSummary = data.data || {};
        document.querySelectorAll('.exam-taker-only').forEach(el => {
            el.classList.toggle('hidden', !canTakeExam(currentUser));
        });
        document.querySelectorAll('.exam-manager-only').forEach(el => {
            el.classList.toggle('hidden', !canManageExam(currentUser));
        });
        if (!canTakeExam(currentUser) && ['practice', 'exam', 'retakes', 'results'].includes(examCurrentTab)) {
            examCurrentTab = 'papers';
        }
        if (!canManageExam(currentUser) && ['papers', 'reviews', 'checkins', 'adminResults'].includes(examCurrentTab)) {
            examCurrentTab = 'practice';
        }
        await showExamTab(examCurrentTab);
    } catch (e) {
        examError(e.message || '考试中心加载失败');
    }
}

async function showExamTab(tab) {
    if (!canTakeExam(currentUser) && ['practice', 'exam', 'retakes', 'results'].includes(tab)) {
        tab = 'papers';
    }
    if (!canManageExam(currentUser) && ['papers', 'reviews', 'checkins', 'adminResults'].includes(tab)) {
        tab = 'practice';
    }
    examCurrentTab = tab;
    document.querySelectorAll('.exam-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.examTab === tab);
    });

    if (tab === 'practice') {
        renderPracticeShell();
    } else if (tab === 'exam') {
        renderExamStart();
    } else if (tab === 'retakes') {
        await loadRetakeEligibilities();
    } else if (tab === 'results') {
        await loadMyExamResults();
    } else if (tab === 'papers') {
        await loadExamPapersAdmin();
    } else if (tab === 'reviews') {
        await loadPendingReviews();
    } else if (tab === 'checkins') {
        await loadCheckinRecords();
    } else if (tab === 'adminResults') {
        await loadAllExamResults();
    }
    examRefreshIcons();
}

function renderPracticeShell() {
    const content = examContent();
    if (!content) return;
    content.innerHTML = `
        <div class="exam-panel">
            <div class="exam-toolbar">
                <div>
                    <h2>随机练习</h2>
                    <p>随机抽取选择题和判断题，提交后显示答案并保存练习记录。</p>
                </div>
                <div class="exam-actions">
                    <button class="btn btn-primary" type="button" onclick="loadRandomPractice()"><i data-lucide="shuffle"></i>开始练习</button>
                    <button class="btn btn-secondary" type="button" onclick="loadPracticeHistory()"><i data-lucide="history"></i>练习记录</button>
                    <button class="btn btn-secondary" type="button" onclick="loadWrongPracticeQuestions()"><i data-lucide="list-x"></i>错题记录</button>
                </div>
            </div>
            <div id="examPracticeDailyStatus" class="exam-summary-card">
                正在加载今日练习打卡状态...
            </div>
            <div id="examAttendanceCalendar" class="exam-summary-card"></div>
            <div id="examPracticeList" class="exam-question-list"></div>
        </div>`;
    loadPracticeDailyStatus();
    loadAttendanceCalendar();
}

async function loadRandomPractice() {
    window.location.href = '/exam/practice-session';
}

async function loadPracticeDailyStatus() {
    const target = document.getElementById('examPracticeDailyStatus');
    if (!target) return;
    try {
        const data = await examJson('/api/exam/practice/daily-status');
        const status = data.data || {};
        const percent = Math.round((status.best_accuracy || 0) * 100);
        target.innerHTML = status.passed
            ? `<strong>今日已合格打卡</strong><span>最高正确率 ${percent}%，已做 ${examEscape(status.answered_count || 0)} 题。</span>`
            : `<strong>今日未合格</strong><span>每日30题以上，正确率达到80%才算合格。当前最高正确率 ${percent}%。</span>`;
    } catch (e) {
        target.innerHTML = `<span>${examEscape(e.message || '今日打卡状态加载失败')}</span>`;
    }
}

function examMonthValue(date = new Date()) {
    const month = String(date.getMonth() + 1).padStart(2, '0');
    return `${date.getFullYear()}-${month}`;
}

async function loadAttendanceCalendar(monthValue = '') {
    const target = document.getElementById('examAttendanceCalendar');
    if (!target) return;
    const month = monthValue || examAttendanceMonth || examMonthValue();
    examAttendanceMonth = month;
    target.innerHTML = '<div class="loading">正在加载打卡日历...</div>';
    try {
        const data = await examJson(`/api/exam/attendance/calendar?month=${encodeURIComponent(month)}`);
        const calendar = data.data || {};
        const days = (calendar.days || []).map(day => {
            const className = day.status === 'passed' ? 'completed' : day.status === 'future' ? 'pending_review' : 'in_progress';
            const click = day.retroactive_allowed ? `onclick="startRetroactivePractice('${examEscape(day.date)}')"` : '';
            return `<button class="btn btn-sm status ${className}" type="button" ${click} title="${examEscape(day.date)} ${Math.round((day.best_accuracy || 0) * 100)}%">${String(day.date || '').slice(-2)}</button>`;
        }).join('');
        target.innerHTML = `
            <div class="exam-toolbar">
                <div>
                    <strong>打卡日历</strong>
                    <p>绿色为合格，红色为未合格或未打卡；可点击历史红色日期补打卡。</p>
                </div>
                <div class="exam-actions">
                    <input type="month" value="${examEscape(calendar.month || month)}" onchange="loadAttendanceCalendar(this.value)">
                </div>
            </div>
            <div class="exam-actions" style="flex-wrap: wrap; gap: 6px;">${days}</div>
            <div class="exam-muted">本月合格 ${calendar.actual_days || 0} 天，未合格/未打卡 ${calendar.missing_days || 0} 天，补打卡 ${calendar.retroactive_used || 0}/${calendar.retroactive_limit || 3} 次。</div>
        `;
    } catch (e) {
        target.innerHTML = `<span>${examEscape(e.message || '打卡日历加载失败')}</span>`;
    }
    examRefreshIcons();
}

function startRetroactivePractice(targetDate) {
    window.location.href = `/exam/practice-session?retroactive_date=${encodeURIComponent(targetDate)}`;
}

async function loadRandomPracticeInline() {
    const list = document.getElementById('examPracticeList') || examContent();
    if (!list) return;
    list.innerHTML = '<div class="loading">正在抽题...</div>';
    try {
        const data = await examJson('/api/exam/practice/random?limit=10');
        const questions = data.data || [];
        list.innerHTML = `
            <form id="examPracticeForm" onsubmit="submitPracticeAnswers(event)">
                ${renderExamQuestions(questions, { mode: 'practice' })}
                <div class="exam-actions">
                    <button class="btn btn-primary" type="submit"><i data-lucide="check"></i>提交练习</button>
                    <button class="btn btn-secondary" type="button" onclick="loadRandomPractice()"><i data-lucide="rotate-cw"></i>换一组</button>
                </div>
                <div id="examPracticeNotice" class="exam-muted"></div>
            </form>`;
        examRefreshIcons();
    } catch (e) {
        list.innerHTML = `<div class="error-message">${examEscape(e.message || '随机练习加载失败')}</div>`;
    }
}

async function submitPracticeAnswers(event) {
    event.preventDefault();
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    try {
        const result = await examJson('/api/exam/practice/submit', {
            method: 'POST',
            body: JSON.stringify({ answers: collectExamAnswers(form) })
        });
        renderPracticeResult(result.data || {});
    } catch (e) {
        if (submitButton) submitButton.disabled = false;
        examNotify(e.message || '练习提交失败', 'error');
    }
}

function answerTextFromOptions(item, value) {
    if (!value) return '-';
    const options = Array.isArray(item.options) ? item.options : [];
    const labels = String(value).split(',').filter(Boolean).map(key => {
        const option = options.find(candidate => candidate.key === key);
        return option ? `${option.key}. ${option.text}` : key;
    });
    return labels.join('，') || value;
}

function examExplanationText(item) {
    const explanation = String(item.reference_answer || '').trim();
    if (explanation) return explanation;
    return `本题正确答案为：${answerTextFromOptions(item, item.correct_answer)}。其余选项与题干要求不符。`;
}

function renderPracticeResult(result) {
    const list = document.getElementById('examPracticeList') || examContent();
    if (!list) return;
    const items = result.items || [];
    const rows = items.map((item, index) => `
        <div class="exam-question ${item.is_correct ? 'exam-correct' : 'exam-wrong'}">
            <div class="exam-question-head">
                <strong>${index + 1}. ${examEscape(item.stem || '')}</strong>
                <span>${item.is_correct ? '正确' : '错误'}</span>
            </div>
            <div class="exam-question-paper">${examEscape(item.paper_title || '')}</div>
            <p><strong>你的答案：</strong>${examEscape(answerTextFromOptions(item, item.answer_text))}</p>
            <p><strong>正确答案：</strong>${examEscape(answerTextFromOptions(item, item.correct_answer))}</p>
            <p><strong>解析：</strong>${examEscape(examExplanationText(item))}</p>
        </div>`).join('');
    list.innerHTML = `
        <div class="exam-toolbar">
            <div>
                <h2>练习结果</h2>
                <p>本次 ${items.length} 题，正确 ${items.filter(item => item.is_correct).length} 题。</p>
            </div>
            <div class="exam-actions">
                <button class="btn btn-primary" type="button" onclick="loadRandomPractice()"><i data-lucide="shuffle"></i>继续练习</button>
                <button class="btn btn-secondary" type="button" onclick="loadWrongPracticeQuestions()"><i data-lucide="list-x"></i>查看错题</button>
            </div>
        </div>
        <div class="exam-question-list">${rows || '<div class="empty-message">暂无练习结果</div>'}</div>`;
    examRefreshIcons();
}

async function loadPracticeHistory() {
    const list = document.getElementById('examPracticeList') || examContent();
    if (!list) return;
    list.innerHTML = '<div class="loading">正在加载练习记录...</div>';
    try {
        const data = await examJson('/api/exam/practice/history');
        renderPracticeRecordList(data.data || [], '暂无练习记录');
    } catch (e) {
        list.innerHTML = `<div class="error-message">${examEscape(e.message || '练习记录加载失败')}</div>`;
    }
}

async function loadWrongPracticeQuestions() {
    const list = document.getElementById('examPracticeList') || examContent();
    if (!list) return;
    list.innerHTML = '<div class="loading">正在加载错题记录...</div>';
    try {
        const data = await examJson('/api/exam/practice/wrong');
        renderPracticeRecordList(data.data || [], '暂无错题记录', { wrongQuestions: true });
    } catch (e) {
        list.innerHTML = `<div class="error-message">${examEscape(e.message || '错题记录加载失败')}</div>`;
    }
}

function renderPracticeRecordList(records, emptyText, options = {}) {
    const list = document.getElementById('examPracticeList') || examContent();
    if (!list) return;
    const rows = records.map((item, index) => `
        <div class="exam-question ${item.is_correct ? 'exam-correct' : 'exam-wrong'}">
            <div class="exam-question-head">
                <strong>${index + 1}. ${examEscape(item.stem || '')}</strong>
                <span>${examEscape(item.created_at || '')}</span>
            </div>
            <div class="exam-question-paper">${examEscape(item.paper_title || '')}</div>
            <p><strong>你的答案：</strong>${examEscape(answerTextFromOptions(item, item.answer_text))}</p>
            <p><strong>正确答案：</strong>${examEscape(answerTextFromOptions(item, item.correct_answer))}</p>
            <p><strong>解析：</strong>${examEscape(examExplanationText(item))}</p>
            <p><strong>结果：</strong>${item.is_correct ? '正确' : '错误'}</p>
        </div>`).join('');
    list.innerHTML = `
        <div class="exam-toolbar">
            <div><h2>${options.wrongQuestions ? '错题记录' : '做题记录'}</h2><p>${options.wrongQuestions ? '答对后会自动从错题记录中移除。' : '可反复查看历史练习和错题。'}</p></div>
            <div class="exam-actions">
                <button class="btn btn-primary" type="button" onclick="loadRandomPractice()"><i data-lucide="shuffle"></i>继续练习</button>
                ${options.wrongQuestions && records.length ? '<button class="btn btn-secondary" type="button" onclick="startWrongPractice()"><i data-lucide="rotate-cw"></i>重新做错题</button>' : ''}
                <button class="btn btn-secondary" type="button" onclick="loadPracticeHistory()"><i data-lucide="history"></i>练习记录</button>
                <button class="btn btn-secondary" type="button" onclick="loadWrongPracticeQuestions()"><i data-lucide="list-x"></i>错题记录</button>
            </div>
        </div>
        <div class="exam-question-list">${rows || `<div class="empty-message">${examEscape(emptyText)}</div>`}</div>`;
    examRefreshIcons();
}

async function startWrongPractice() {
    const list = document.getElementById('examPracticeList') || examContent();
    if (!list) return;
    list.innerHTML = '<div class="loading">正在加载错题...</div>';
    try {
        const data = await examJson('/api/exam/practice/wrong/questions');
        const questions = data.data || [];
        if (!questions.length) {
            renderPracticeRecordList([], '暂无需要重做的错题', { wrongQuestions: true });
            return;
        }
        list.innerHTML = `
            <form id="examWrongPracticeForm" onsubmit="submitWrongPracticeAnswers(event)">
                ${renderExamQuestions(questions, { mode: 'practice' })}
                <div class="exam-actions">
                    <button class="btn btn-primary" type="submit"><i data-lucide="check"></i>提交错题重做</button>
                    <button class="btn btn-secondary" type="button" onclick="loadWrongPracticeQuestions()"><i data-lucide="arrow-left"></i>返回错题记录</button>
                </div>
            </form>`;
        examRefreshIcons();
    } catch (e) {
        list.innerHTML = `<div class="error-message">${examEscape(e.message || '错题加载失败')}</div>`;
    }
}

async function submitWrongPracticeAnswers(event) {
    event.preventDefault();
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    try {
        const result = await examJson('/api/exam/practice/wrong/submit', {
            method: 'POST',
            body: JSON.stringify({ answers: collectExamAnswers(form) })
        });
        renderWrongPracticeResult(result.data || {});
    } catch (e) {
        if (submitButton) submitButton.disabled = false;
        examNotify(e.message || '错题提交失败', 'error');
    }
}

function renderWrongPracticeResult(result) {
    const list = document.getElementById('examPracticeList') || examContent();
    if (!list) return;
    const items = result.items || [];
    const rows = items.map((item, index) => `
        <div class="exam-question ${item.is_correct ? 'exam-correct' : 'exam-wrong'}">
            <div class="exam-question-head">
                <strong>${index + 1}. ${examEscape(item.stem || '')}</strong>
                <span>${item.is_correct ? '正确' : '错误'}</span>
            </div>
            <div class="exam-question-paper">${examEscape(item.paper_title || '')}</div>
            <p><strong>你的答案：</strong>${examEscape(answerTextFromOptions(item, item.answer_text))}</p>
            <p><strong>正确答案：</strong>${examEscape(answerTextFromOptions(item, item.correct_answer))}</p>
            <p><strong>解析：</strong>${examEscape(examExplanationText(item))}</p>
        </div>`).join('');
    list.innerHTML = `
        <div class="exam-toolbar">
            <div><h2>错题重做结果</h2><p>本次答对并移除 ${examEscape(result.resolved_count || 0)} 题，剩余 ${examEscape(result.remaining_count || 0)} 题。</p></div>
            <div class="exam-actions">
                <button class="btn btn-primary" type="button" onclick="loadWrongPracticeQuestions()"><i data-lucide="list-x"></i>查看剩余错题</button>
            </div>
        </div>
        <div class="exam-question-list">${rows}</div>`;
    examRefreshIcons();
}

function renderExamStart() {
    const paper = examSummary?.current_paper;
    const content = examContent();
    if (!content) return;
    const canStart = canTakeExam(currentUser);
    const managerOnly = canManageExam(currentUser) && !canStart;
    const startButton = paper && canStart
        ? '<button class="btn btn-primary" type="button" onclick="startCurrentExam()"><i data-lucide="play"></i>开始考试</button>'
        : '';
    const managerOnlyNotice = managerOnly
        ? '<div class="exam-muted">当前账号仅可管理考试，不能参加正式考试。</div>'
        : '';
    content.innerHTML = `
        <div class="exam-panel">
            <div class="exam-toolbar">
                <div>
                    <h2>正式考试</h2>
                    <p>${paper ? `当前试卷：${examEscape(paper.title)}，时长 ${examEscape(paper.duration_minutes || '-')} 分钟，总分 ${examScore(paper.total_score)}` : '管理员尚未设置当前试卷。'}</p>
                </div>
                ${startButton}
            </div>
            ${managerOnlyNotice}
            <div id="examAttemptArea"></div>
        </div>`;
}

async function startCurrentExam() {
    const area = document.getElementById('examAttemptArea') || examContent();
    if (!area) return;
    if (!canTakeExam(currentUser)) {
        area.innerHTML = '<div class="error-message">当前账号仅可管理考试，不能参加正式考试。</div>';
        return;
    }
    if (!confirm('开始正式考试后请一次性提交，确认开始？')) return;
    area.innerHTML = '<div class="loading">正在创建考试...</div>';
    try {
        const started = await examJson('/api/exam/attempts', {
            method: 'POST',
            body: JSON.stringify({ paper_id: examSummary?.current_paper?.id })
        });
        const attemptId = started.attempt_id || started.data?.attempt_id || started.data?.id;
        const detail = await examJson(`/api/exam/attempts/${attemptId}`);
        examActiveAttempt = detail.data;
        area.innerHTML = `
            <form id="examAttemptForm" onsubmit="submitExamAttempt(event, ${Number(attemptId)})">
                ${renderExamQuestions(examActiveAttempt.questions || [], { mode: 'exam' })}
                <div class="exam-actions">
                    <button class="btn btn-primary" type="submit"><i data-lucide="send"></i>提交试卷</button>
                </div>
            </form>`;
        examRefreshIcons();
    } catch (e) {
        area.innerHTML = `<div class="error-message">${examEscape(e.message || '考试创建失败')}</div>`;
    }
}

function renderExamQuestions(questions, options = {}) {
    if (!questions.length) {
        return '<div class="empty-message">暂无题目</div>';
    }
    return questions.map((question, index) => {
        const type = question.question_type || '';
        const inputName = `q_${question.id}`;
        const optionHtml = renderQuestionOptions(question, inputName, options.mode);
        const paperTitle = question.paper_title ? `<div class="exam-question-paper">${examEscape(question.paper_title)}</div>` : '';
        return `
            <div class="exam-question" data-question-id="${question.id}" data-question-type="${examEscape(type)}">
                <div class="exam-question-head">
                    <strong>${index + 1}. ${examEscape(question.stem || '')}</strong>
                    <span>${examScore(question.score)} 分</span>
                </div>
                ${paperTitle}
                ${optionHtml}
            </div>`;
    }).join('');
}

function renderQuestionOptions(question, inputName, mode) {
    const type = question.question_type;
    const options = ensureTrueFalseOptions(question);
    if (type === 'single_choice' || type === 'true_false') {
        return `<div class="exam-options">${options.map(option => `
            <label class="exam-option">
                <input type="radio" name="${inputName}" value="${examEscape(option.key)}">
                <span>${examEscape(option.key)}. ${examEscape(option.text)}</span>
            </label>`).join('')}</div>`;
    }
    if (type === 'multiple_choice') {
        return `<div class="exam-options">${options.map(option => `
            <label class="exam-option">
                <input type="checkbox" name="${inputName}" value="${examEscape(option.key)}">
                <span>${examEscape(option.key)}. ${examEscape(option.text)}</span>
            </label>`).join('')}</div>`;
    }
    return `<textarea class="exam-answer-text" name="${inputName}" rows="${mode === 'exam' ? 5 : 3}" placeholder="请输入作答内容"></textarea>`;
}

function ensureTrueFalseOptions(question) {
    if (question.question_type !== 'true_false') {
        return Array.isArray(question.options) ? question.options : [];
    }
    const options = Array.isArray(question.options) ? question.options.filter(option => option.key) : [];
    return options.length ? options : [
        { key: '√', text: '正确' },
        { key: '×', text: '错误' }
    ];
}

function collectExamAnswers(form) {
    const answers = {};
    form.querySelectorAll('.exam-question').forEach(questionEl => {
        const questionId = questionEl.dataset.questionId;
        const type = questionEl.dataset.questionType;
        const name = `q_${questionId}`;
        if (type === 'multiple_choice') {
            answers[questionId] = Array.from(form.querySelectorAll(`input[name="${name}"]:checked`)).map(input => input.value).join(',');
        } else if (EXAM_OBJECTIVE_TYPES.includes(type)) {
            answers[questionId] = form.querySelector(`input[name="${name}"]:checked`)?.value || '';
        } else {
            answers[questionId] = form.querySelector(`[name="${name}"]`)?.value || '';
        }
    });
    return answers;
}

async function submitExamAttempt(event, attemptId) {
    event.preventDefault();
    if (!confirm('确认提交试卷？提交后不能重复交卷。')) return;
    const form = event.target;
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    try {
        const result = await examJson(`/api/exam/attempts/${attemptId}/submit`, {
            method: 'POST',
            body: JSON.stringify({ answers: collectExamAnswers(form) })
        });
        examNotify('试卷已提交', 'success');
        renderAttemptReview(result.data || {});
    } catch (e) {
        if (submitButton) submitButton.disabled = false;
        examNotify(e.message || '提交失败', 'error');
    }
}

async function loadMyExamResults() {
    examLoading('正在加载我的成绩...');
    try {
        const data = await examJson('/api/exam/results');
        renderResultsTable(data.data || [], { admin: false });
    } catch (e) {
        examError(e.message || '成绩加载失败');
    }
}

function retakeTypeText(type) {
    if (type === 'makeup_absent') return '缺考补考';
    if (type === 'retake_failed') return '不合格重考';
    return type || '-';
}

async function loadRetakeEligibilities() {
    examLoading('正在加载补考/重考资格...');
    try {
        const data = await examJson('/api/exam/retake/eligibilities');
        const rows = data.data || [];
        const grouped = {
            makeup_absent: rows.filter(row => row.eligibility_type === 'makeup_absent'),
            retake_failed: rows.filter(row => row.eligibility_type === 'retake_failed')
        };
        const renderGroup = (title, typeRows) => {
            const body = typeRows.map(row => `
                <tr>
                    <td>${examEscape(row.paper_title || '-')}</td>
                    <td>${examEscape(row.reason || '-')}</td>
                    <td>${examDate(row.created_at)}</td>
                    <td><button class="btn btn-primary btn-sm" type="button" onclick="startRetakeEligibility(${Number(row.id)})">开始</button></td>
                </tr>`).join('');
            return `
                <section class="exam-panel">
                    <div class="exam-toolbar"><h3>${title}</h3></div>
                    <div class="table-container">
                        <table>
                            <thead><tr><th>试卷</th><th>原因</th><th>生成时间</th><th>操作</th></tr></thead>
                            <tbody>${body || '<tr><td colspan="4" class="empty-message">暂无资格</td></tr>'}</tbody>
                        </table>
                    </div>
                </section>`;
        };
        examContent().innerHTML = `
            ${renderGroup('缺考补考', grouped.makeup_absent)}
            ${renderGroup('不合格重考', grouped.retake_failed)}
        `;
    } catch (e) {
        examError(e.message || '补考/重考资格加载失败');
    }
    examRefreshIcons();
}

async function startRetakeEligibility(eligibilityId) {
    try {
        const result = await examJson(`/api/exam/retake/eligibilities/${eligibilityId}/start`, {
            method: 'POST',
            body: JSON.stringify({})
        });
        examActiveAttempt = result.data;
        await renderAttempt(result.attempt_id || result.data?.attempt_id || result.data?.id);
    } catch (e) {
        examNotify(e.message || '启动补考/重考失败', 'error');
    }
}

async function loadExamPapersAdmin() {
    if (!canManageExam(currentUser)) return;
    examLoading('正在加载题库...');
    try {
        const [papers, summary] = await Promise.all([
            examJson('/api/exam/admin/papers'),
            examJson('/api/exam/summary')
        ]);
        examSummary = summary.data || examSummary;
        const currentId = examSummary?.current_paper?.id;
        const rows = (papers.data || []).map(paper => {
            const isCurrent = Number(paper.id) === Number(currentId);
            const action = isCurrent
                ? '<button class="btn btn-warning btn-sm" type="button" onclick="clearCurrentExamPaper()">取消当前</button>'
                : `<button class="btn btn-secondary btn-sm" type="button" onclick="setCurrentExamPaper(${paper.id})">设为当前</button>`;
            return `
            <tr>
                <td>${examEscape(paper.title)}</td>
                <td>${examEscape(paper.source_type || '-')}</td>
                <td>${examEscape(paper.duration_minutes || '-')}</td>
                <td>${examScore(paper.total_score)}</td>
                <td>${isCurrent ? '<span class="badge badge-ok">当前</span>' : ''}${action}</td>
            </tr>`;
        }).join('');
        examContent().innerHTML = `
            <div class="exam-panel">
                <div class="exam-toolbar"><h2>题库管理</h2><button class="btn btn-secondary" type="button" onclick="loadExamPapersAdmin()"><i data-lucide="refresh-cw"></i>刷新</button></div>
                <div class="table-container"><table><thead><tr><th>试卷</th><th>来源</th><th>时长</th><th>总分</th><th>操作</th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="empty-message">暂无试卷</td></tr>'}</tbody></table></div>
            </div>`;
        examRefreshIcons();
    } catch (e) {
        examError(e.message || '题库加载失败');
    }
}

async function setCurrentExamPaper(paperId) {
    try {
        await examJson('/api/exam/admin/current-paper', {
            method: 'POST',
            body: JSON.stringify({ paper_id: paperId })
        });
        examNotify('当前试卷已更新', 'success');
        await loadExamPapersAdmin();
    } catch (e) {
        examNotify(e.message || '设置失败', 'error');
    }
}

async function clearCurrentExamPaper() {
    if (!confirm('确认取消当前正式考试试卷？取消后材料员将不能进入正式考试。')) return;
    try {
        await examJson('/api/exam/admin/current-paper', {
            method: 'DELETE'
        });
        examSummary = {
            ...(examSummary || {}),
            current_paper: null
        };
        examNotify('已取消当前试卷', 'success');
        await loadExamPapersAdmin();
    } catch (e) {
        examNotify(e.message || '取消失败', 'error');
    }
}

async function loadPendingReviews() {
    if (!canManageExam(currentUser)) return;
    examLoading('正在加载待阅卷题目...');
    try {
        const data = await examJson('/api/exam/admin/reviews');
        const rows = (data.data || []).map(item => `
            <div class="exam-question">
                <div class="exam-question-head">
                    <strong>${examEscape(item.user_name || item.username || '-')} - ${examEscape(item.paper_title || '-')}</strong>
                    <span>${examScore(item.score)} 分</span>
                </div>
                <p><strong>题目：</strong>${examEscape(item.stem || '')}</p>
                <p><strong>作答：</strong>${examEscape(item.answer_text || '-')}</p>
                <p><strong>参考：</strong>${examEscape(item.reference_answer || '-')}</p>
                <div class="exam-review-form">
                    <input type="number" min="0" max="${examEscape(item.score || '')}" step="0.5" id="reviewScore${item.answer_id}" value="${examEscape(item.suggested_score ?? '')}" placeholder="分数">
                    <input type="text" id="reviewComment${item.answer_id}" placeholder="阅卷意见">
                    <button class="btn btn-primary" type="button" onclick="submitReviewScore(${item.answer_id})">提交评分</button>
                </div>
            </div>`).join('');
        examContent().innerHTML = `
            <div class="exam-panel">
                <div class="exam-toolbar"><h2>阅卷</h2><button class="btn btn-secondary" type="button" onclick="loadPendingReviews()"><i data-lucide="refresh-cw"></i>刷新</button></div>
                <div class="exam-question-list">${rows || '<div class="empty-message">暂无待阅卷题目</div>'}</div>
            </div>`;
        examRefreshIcons();
    } catch (e) {
        examError(e.message || '阅卷列表加载失败');
    }
}

async function submitReviewScore(answerId) {
    const score = document.getElementById(`reviewScore${answerId}`)?.value;
    const comment = document.getElementById(`reviewComment${answerId}`)?.value || '';
    try {
        await examJson(`/api/exam/admin/reviews/${answerId}`, {
            method: 'POST',
            body: JSON.stringify({ final_score: score, comment })
        });
        examNotify('评分已提交', 'success');
        await loadPendingReviews();
    } catch (e) {
        examNotify(e.message || '评分失败', 'error');
    }
}

async function loadAllExamResults() {
    if (!canManageExam(currentUser)) return;
    examLoading('正在加载成绩...');
    try {
        const data = await examJson('/api/exam/admin/results');
        renderResultsTable(data.data || [], { admin: true });
    } catch (e) {
        examError(e.message || '成绩查询加载失败');
    }
}

function todayDateValue() {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${now.getFullYear()}-${month}-${day}`;
}

async function loadCheckinRecords() {
    if (!canManageExam(currentUser)) return;
    const existingDate = document.getElementById('examCheckinDate')?.value || todayDateValue();
    examLoading('正在加载打卡记录...');
    try {
        const data = await examJson(`/api/exam/admin/checkins?date=${encodeURIComponent(existingDate)}`);
        examCheckinRecords = data.data || [];
        renderCheckinRecords(existingDate);
    } catch (e) {
        examError(e.message || '打卡记录加载失败');
    }
}

async function loadMonthlyCheckinReport() {
    if (!canManageExam(currentUser)) return;
    const monthValue = document.getElementById('examCheckinMonth')?.value || examMonthValue();
    const target = document.getElementById('examMonthlyCheckinReport');
    if (!target) return;
    target.innerHTML = '<div class="loading">正在加载月度对账...</div>';
    try {
        const data = await examJson(`/api/exam/admin/checkins/monthly?month=${encodeURIComponent(monthValue)}`);
        const rows = (data.data || []).map(row => `
            <tr>
                <td>${examEscape(row.real_name || row.username || '-')}</td>
                <td>${examEscape(row.username || '-')}</td>
                <td>${examEscape(row.role_name || '-')}</td>
                <td>${examEscape(row.expected_days || 0)}</td>
                <td>${examEscape(row.actual_days || 0)}</td>
                <td>${examEscape(row.missing_days || 0)}</td>
                <td>${examEscape(row.retroactive_used || 0)}</td>
            </tr>`).join('');
        target.innerHTML = `
            <div class="table-container">
                <table>
                    <thead><tr><th>姓名</th><th>账号</th><th>角色</th><th>应打卡</th><th>实际合格</th><th>未合格/未打卡</th><th>补打卡</th></tr></thead>
                    <tbody>${rows || '<tr><td colspan="7" class="empty-message">暂无月报数据</td></tr>'}</tbody>
                </table>
            </div>`;
    } catch (e) {
        target.innerHTML = `<div class="error-message">${examEscape(e.message || '月度对账加载失败')}</div>`;
    }
}

function setCheckinFilter(filter) {
    examCheckinFilter = filter;
    const dateValue = document.getElementById('examCheckinDate')?.value || todayDateValue();
    renderCheckinRecords(dateValue);
}

function filteredCheckinRecords() {
    if (examCheckinFilter === 'passed') {
        return examCheckinRecords.filter(row => row.passed);
    }
    if (examCheckinFilter === 'failed') {
        return examCheckinRecords.filter(row => row.practiced && !row.passed);
    }
    if (examCheckinFilter === 'missing') {
        return examCheckinRecords.filter(row => !row.practiced);
    }
    return examCheckinRecords;
}

function checkinStatusText(row) {
    if (row.passed) return '已合格';
    if (row.practiced) return '已做未合格';
    return '未做题';
}

function renderCheckinRecords(dateValue) {
    const rows = filteredCheckinRecords().map(row => `
        <tr>
            <td>${examEscape(row.real_name || row.username || '-')}</td>
            <td>${examEscape(row.username || '-')}</td>
            <td>${examEscape(row.role_name || '-')}</td>
            <td><span class="status ${row.passed ? 'completed' : row.practiced ? 'pending_review' : 'in_progress'}">${checkinStatusText(row)}</span></td>
            <td>${examEscape(row.answered_count || 0)}</td>
            <td>${examEscape(row.session_count || 0)}</td>
            <td>${Math.round((row.best_accuracy || 0) * 100)}%</td>
            <td>${examDate(row.latest_practice_at)}</td>
        </tr>`).join('');
    examContent().innerHTML = `
        <div class="exam-panel">
            <div class="exam-toolbar">
                <div>
                    <h2>打卡记录</h2>
                    <p>查看每日谁已做题、谁未做题，以及是否达到80%合格线。</p>
                </div>
                <div class="exam-actions">
                    <input id="examCheckinDate" type="date" value="${examEscape(dateValue)}" onchange="loadCheckinRecords()">
                    <button class="btn btn-secondary" type="button" onclick="loadCheckinRecords()"><i data-lucide="refresh-cw"></i>刷新</button>
                </div>
            </div>
            <div class="exam-actions">
                <button class="btn ${examCheckinFilter === 'all' ? 'btn-primary' : 'btn-secondary'}" data-checkin-filter="all" type="button" onclick="setCheckinFilter('all')">全部</button>
                <button class="btn ${examCheckinFilter === 'passed' ? 'btn-primary' : 'btn-secondary'}" data-checkin-filter="passed" type="button" onclick="setCheckinFilter('passed')">已合格</button>
                <button class="btn ${examCheckinFilter === 'failed' ? 'btn-primary' : 'btn-secondary'}" data-checkin-filter="failed" type="button" onclick="setCheckinFilter('failed')">已做未合格</button>
                <button class="btn ${examCheckinFilter === 'missing' ? 'btn-primary' : 'btn-secondary'}" data-checkin-filter="missing" type="button" onclick="setCheckinFilter('missing')">未做题</button>
                <input id="examCheckinMonth" type="month" value="${examEscape(String(dateValue || todayDateValue()).slice(0, 7))}">
                <button class="btn btn-secondary" type="button" onclick="loadMonthlyCheckinReport()"><i data-lucide="calendar-days"></i>月度对账</button>
            </div>
            <div class="table-container">
                <table>
                    <thead><tr><th>姓名</th><th>账号</th><th>角色</th><th>打卡状态</th><th>已做题数</th><th>练习次数</th><th>最高正确率</th><th>最近练习</th></tr></thead>
                    <tbody>${rows || '<tr><td colspan="8" class="empty-message">暂无打卡记录</td></tr>'}</tbody>
                </table>
            </div>
            <div id="examMonthlyCheckinReport" class="exam-summary-card"></div>
        </div>`;
    examRefreshIcons();
}

function renderResultsTable(results, options = {}) {
    const rows = results.map(row => `
        <tr>
            ${options.admin ? `<td>${examEscape(row.user_name || row.username || '-')}</td><td>${examEscape(row.role_name || '-')}</td>` : ''}
            <td>${examEscape(row.paper_title || '-')}</td>
            <td><span class="status ${examEscape(row.status || '')}">${examStatusText(row.status)}</span></td>
            <td>${examScore(row.objective_score)}</td>
            <td>${examScore(row.final_subjective_score ?? row.suggested_subjective_score)}</td>
            <td><strong>${examScore(row.final_score)}</strong></td>
            <td>${examDate(row.submitted_at || row.started_at)}</td>
            <td>
                <button class="btn btn-secondary btn-sm" type="button" onclick="viewExamAttemptReview(${Number(row.attempt_id || row.id)})">查看明细</button>
                ${options.admin ? `<button class="btn btn-danger btn-sm" type="button" onclick="deleteExamAttempt(${Number(row.attempt_id || row.id)})">删除</button>` : ''}
            </td>
        </tr>`).join('');
    const heading = options.admin ? '成绩查询' : '我的成绩';
    const adminHeaders = options.admin ? '<th>姓名</th><th>角色</th>' : '';
    examContent().innerHTML = `
        <div class="exam-panel">
            <div class="exam-toolbar"><h2>${heading}</h2><button class="btn btn-secondary" type="button" onclick="${options.admin ? 'loadAllExamResults' : 'loadMyExamResults'}()"><i data-lucide="refresh-cw"></i>刷新</button></div>
            <div class="table-container">
                <table>
                    <thead><tr>${adminHeaders}<th>试卷</th><th>状态</th><th>客观题</th><th>主观题</th><th>总分</th><th>时间</th><th>操作</th></tr></thead>
                    <tbody>${rows || `<tr><td colspan="${options.admin ? 9 : 7}" class="empty-message">暂无成绩</td></tr>`}</tbody>
                </table>
            </div>
        </div>`;
    examRefreshIcons();
}

async function deleteExamAttempt(attemptId) {
    if (!canManageExam(currentUser)) return;
    if (!confirm('确认删除这条正式考试成绩？删除后不可恢复。')) return;
    try {
        await examJson(`/api/exam/admin/attempts/${attemptId}`, {
            method: 'DELETE'
        });
        examNotify('成绩已删除', 'success');
        await loadAllExamResults();
    } catch (e) {
        examNotify(e.message || '删除成绩失败', 'error');
    }
}

async function viewExamAttemptReview(attemptId) {
    examLoading('正在加载答题明细...');
    try {
        const data = await examJson(`/api/exam/attempts/${attemptId}/review`);
        renderAttemptReview(data.data || {});
    } catch (e) {
        examError(e.message || '答题明细加载失败');
    }
}

function renderAttemptReview(review) {
    const attempt = review.attempt || {};
    const items = review.items || [];
    const rows = items.map((item, index) => `
        <div class="exam-question ${item.is_correct === true ? 'exam-correct' : item.is_correct === false ? 'exam-wrong' : ''}">
            <div class="exam-question-head">
                <strong>${index + 1}. ${examEscape(item.stem || '')}</strong>
                <span>${examScore(item.final_score ?? item.auto_score ?? item.suggested_score)} / ${examScore(item.score)}</span>
            </div>
            <p><strong>你的答案：</strong>${examEscape(answerTextFromOptions(item, item.answer_text))}</p>
            ${item.correct_answer ? `<p><strong>正确答案：</strong>${examEscape(answerTextFromOptions(item, item.correct_answer))}</p>` : ''}
            ${item.reference_answer ? `<p><strong>参考：</strong>${examEscape(item.reference_answer)}</p>` : ''}
            ${item.is_correct === null || item.is_correct === undefined ? '' : `<p><strong>结果：</strong>${item.is_correct ? '正确' : '错误'}</p>`}
        </div>`).join('');
    examContent().innerHTML = `
        <div class="exam-panel">
            <div class="exam-toolbar">
                <div>
                    <h2>答题明细</h2>
                    <p>${examEscape(attempt.paper_title || '-')} · ${examStatusText(attempt.status)}</p>
                </div>
                <button class="btn btn-secondary" type="button" onclick="${canManageExam(currentUser) ? 'loadAllExamResults()' : 'loadMyExamResults()'}"><i data-lucide="arrow-left"></i>返回成绩</button>
            </div>
            <div class="exam-question-list">${rows || '<div class="empty-message">暂无答题明细</div>'}</div>
        </div>`;
    examRefreshIcons();
}
