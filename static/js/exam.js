let examSummary = null;
let examCurrentTab = 'practice';
let examActiveAttempt = null;

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
        document.querySelectorAll('.exam-manager-only').forEach(el => {
            el.classList.toggle('hidden', !canManageExam(currentUser));
        });
        if (!canManageExam(currentUser) && ['papers', 'reviews', 'adminResults'].includes(examCurrentTab)) {
            examCurrentTab = 'practice';
        }
        await showExamTab(examCurrentTab);
    } catch (e) {
        examError(e.message || '考试中心加载失败');
    }
}

async function showExamTab(tab) {
    if (!canManageExam(currentUser) && ['papers', 'reviews', 'adminResults'].includes(tab)) {
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
    } else if (tab === 'results') {
        await loadMyExamResults();
    } else if (tab === 'papers') {
        await loadExamPapersAdmin();
    } else if (tab === 'reviews') {
        await loadPendingReviews();
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
                    <p>随机抽题用于自测，不显示答案。</p>
                </div>
                <button class="btn btn-primary" type="button" onclick="loadRandomPractice()"><i data-lucide="shuffle"></i>开始练习</button>
            </div>
            <div id="examPracticeList" class="exam-question-list"></div>
        </div>`;
}

async function loadRandomPractice() {
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
                    <button class="btn btn-primary" type="submit"><i data-lucide="check"></i>完成练习</button>
                    <button class="btn btn-secondary" type="button" onclick="loadRandomPractice()"><i data-lucide="rotate-cw"></i>换一组</button>
                </div>
                <div id="examPracticeNotice" class="exam-muted"></div>
            </form>`;
        examRefreshIcons();
    } catch (e) {
        list.innerHTML = `<div class="error-message">${examEscape(e.message || '随机练习加载失败')}</div>`;
    }
}

function submitPracticeAnswers(event) {
    event.preventDefault();
    const notice = document.getElementById('examPracticeNotice');
    if (notice) {
        notice.textContent = '已记录本次作答。练习模式不显示答案，正式成绩请进入正式考试提交。';
    }
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
    const options = Array.isArray(question.options) ? question.options : [];
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
        await examJson(`/api/exam/attempts/${attemptId}/submit`, {
            method: 'POST',
            body: JSON.stringify({ answers: collectExamAnswers(form) })
        });
        examNotify('试卷已提交', 'success');
        await loadMyExamResults();
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
        const rows = (papers.data || []).map(paper => `
            <tr>
                <td>${examEscape(paper.title)}</td>
                <td>${examEscape(paper.source_type || '-')}</td>
                <td>${examEscape(paper.duration_minutes || '-')}</td>
                <td>${examScore(paper.total_score)}</td>
                <td>${Number(paper.id) === Number(currentId) ? '<span class="badge badge-ok">当前</span>' : `<button class="btn btn-secondary btn-sm" type="button" onclick="setCurrentExamPaper(${paper.id})">设为当前</button>`}</td>
            </tr>`).join('');
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
        </tr>`).join('');
    const heading = options.admin ? '成绩查询' : '我的成绩';
    const adminHeaders = options.admin ? '<th>姓名</th><th>角色</th>' : '';
    examContent().innerHTML = `
        <div class="exam-panel">
            <div class="exam-toolbar"><h2>${heading}</h2><button class="btn btn-secondary" type="button" onclick="${options.admin ? 'loadAllExamResults' : 'loadMyExamResults'}()"><i data-lucide="refresh-cw"></i>刷新</button></div>
            <div class="table-container">
                <table>
                    <thead><tr>${adminHeaders}<th>试卷</th><th>状态</th><th>客观题</th><th>主观题</th><th>总分</th><th>时间</th></tr></thead>
                    <tbody>${rows || `<tr><td colspan="${options.admin ? 8 : 6}" class="empty-message">暂无成绩</td></tr>`}</tbody>
                </table>
            </div>
        </div>`;
    examRefreshIcons();
}
