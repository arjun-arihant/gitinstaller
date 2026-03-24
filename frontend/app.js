/**
 * GitInstaller — app.js
 * Frontend logic: screens, API bridge, plan review, cancel, search, themes,
 * drag-drop, shortcuts, terminal scroll pinning, uninstall, update, accessibility.
 */

// ==================== State ====================
let currentInstallPlan = null;
let currentProjectMeta = null;
let currentRepoUrl = '';
let stepsCompleted = 0;
let totalSteps = 0;
let failedStepId = null;
let terminalCollapsed = false;
let terminalPinned = true;  // true = auto-scroll to bottom
let isInstalling = false;   // true while install is in progress

// ==================== DOM Ready ====================
window.addEventListener('pywebviewready', function () {
    initApp();
});

async function initApp() {
    try {
        const path = await pyApi().get_install_path();
        document.getElementById('install-path').textContent = path || '~/GitInstaller';

        const key = await pyApi().get_api_key();
        toggleApiWarning(!key);

        // Load theme
        const theme = await pyApi().get_theme();
        applyTheme(theme || 'dark');

        // Display version
        try {
            const version = await pyApi().get_version();
            const versionEl = document.getElementById('app-version');
            if (versionEl && version) versionEl.textContent = 'v' + version;
        } catch (_) { /* version endpoint optional */ }

        await refreshProjectList();
    } catch (e) {
        console.error('Init error:', e);
    }

    bindEvents();
}

function pyApi() {
    return window.pywebview.api;
}

// ==================== Event Binding ====================
function bindEvents() {
    // Settings modal
    document.getElementById('btn-settings').addEventListener('click', openSettings);
    document.getElementById('btn-modal-close').addEventListener('click', closeSettings);
    document.getElementById('modal-settings').addEventListener('click', function (e) {
        if (e.target === this) closeSettings();
    });
    document.getElementById('btn-save-settings').addEventListener('click', saveSettings);
    document.getElementById('btn-toggle-password').addEventListener('click', function () {
        togglePasswordField('api-key-input', this);
    });
    document.getElementById('btn-toggle-gh-token').addEventListener('click', function () {
        togglePasswordField('github-token-input', this);
    });

    // Theme toggle
    document.getElementById('btn-theme-toggle').addEventListener('click', toggleTheme);

    // Folder picker
    document.getElementById('btn-change-folder').addEventListener('click', pickFolder);

    // Install
    document.getElementById('btn-install').addEventListener('click', startAnalyze);

    // URL input
    document.getElementById('repo-url').addEventListener('input', function () {
        document.getElementById('url-error').textContent = '';
    });

    document.getElementById('repo-url').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') startAnalyze();
    });

    // Drag and drop
    var dropZone = document.getElementById('drop-zone');
    dropZone.addEventListener('dragover', function (e) {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    dropZone.addEventListener('dragleave', function () {
        dropZone.classList.remove('drag-over');
    });
    dropZone.addEventListener('drop', function (e) {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        var text = e.dataTransfer.getData('text/plain') || e.dataTransfer.getData('text/uri-list');
        if (text) {
            document.getElementById('repo-url').value = text.trim();
            document.getElementById('url-error').textContent = '';
        }
    });

    // Plan review buttons
    document.getElementById('btn-plan-cancel').addEventListener('click', function () {
        showScreen('screen-home');
    });
    document.getElementById('btn-approve-install').addEventListener('click', approveInstall);

    // Error go back
    document.getElementById('btn-error-back').addEventListener('click', function () {
        resetInstallBtn();
        showScreen('screen-home');
    });

    // Cancel install — show confirmation if mid-install
    document.getElementById('btn-cancel-install').addEventListener('click', function () {
        if (isInstalling) {
            showConfirm(
                'Cancel Installation?',
                'Are you sure you want to cancel? Partial files may remain on disk.',
                '⚠️',
                function () { pyApi().cancel_install(); }
            );
        } else {
            pyApi().cancel_install();
        }
    });

    // Terminal toggle
    document.getElementById('btn-toggle-terminal').addEventListener('click', toggleTerminal);

    // Scroll to bottom button
    document.getElementById('btn-scroll-bottom').addEventListener('click', function () {
        pinTerminal();
        scrollTerminalToBottom();
    });

    // Terminal scroll event — detect when user scrolls up
    document.getElementById('terminal').addEventListener('scroll', function () {
        var t = this;
        var atBottom = t.scrollHeight - t.scrollTop - t.clientHeight < 50;
        if (atBottom) {
            pinTerminal();
        } else {
            unpinTerminal();
        }
    });

    // Copy log
    document.getElementById('btn-copy-log').addEventListener('click', copyLog);

    // Retry / Skip
    document.getElementById('btn-retry-step').addEventListener('click', retryStep);
    document.getElementById('btn-skip-step').addEventListener('click', skipStep);

    // Done screen
    document.getElementById('btn-done-launch').addEventListener('click', function () {
        if (currentProjectMeta && currentProjectMeta.project_id) {
            pyApi().launch_project(currentProjectMeta.project_id);
        }
    });
    document.getElementById('btn-done-another').addEventListener('click', function () {
        resetState();
        refreshProjectList();
        showScreen('screen-home');
    });
    var donePath = document.getElementById('done-path');
    donePath.addEventListener('click', openCurrentProjectFolder);
    donePath.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') openCurrentProjectFolder();
    });

    // Cancelled screen
    document.getElementById('btn-cancelled-home').addEventListener('click', function () {
        resetState();
        refreshProjectList();
        showScreen('screen-home');
    });

    // WebUI buttons
    document.getElementById('btn-build-webui').addEventListener('click', function () {
        document.getElementById('webui-offer').classList.add('hidden');
        document.getElementById('webui-building').classList.remove('hidden');
        pyApi().build_project_webui();
    });
    document.getElementById('btn-skip-webui').addEventListener('click', function () {
        document.getElementById('webui-offer').classList.add('hidden');
    });
    document.getElementById('btn-launch-webui').addEventListener('click', function () {
        if (currentProjectMeta && currentProjectMeta.project_id) {
            pyApi().launch_webui(currentProjectMeta.project_id);
        }
    });

    // Search
    document.getElementById('search-input').addEventListener('input', filterProjects);

    // Confirm dialog
    document.getElementById('btn-confirm-cancel').addEventListener('click', hideConfirm);
    document.getElementById('modal-confirm').addEventListener('click', function (e) {
        if (e.target === this) hideConfirm();
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function (e) {
        // Escape closes modals
        if (e.key === 'Escape') {
            var confirmModal = document.getElementById('modal-confirm');
            var settingsModal = document.getElementById('modal-settings');
            if (!confirmModal.classList.contains('hidden')) {
                hideConfirm();
            } else if (!settingsModal.classList.contains('hidden')) {
                closeSettings();
            }
        }
        // Ctrl+V focuses URL input if on home screen
        if ((e.ctrlKey || e.metaKey) && e.key === 'v') {
            var homeScreen = document.getElementById('screen-home');
            if (homeScreen.classList.contains('active')) {
                document.getElementById('repo-url').focus();
            }
        }
    });
}

// ==================== Screen Navigation ====================
function showScreen(screenId, direction) {
    var screens = document.querySelectorAll('.screen');
    screens.forEach(function (s) {
        s.classList.remove('active', 'slide-left', 'slide-right');
    });
    var target = document.getElementById(screenId);
    if (target) {
        if (direction === 'left') {
            target.classList.add('slide-left');
        } else if (direction === 'right') {
            target.classList.add('slide-right');
        }
        target.classList.add('active');
    }
}

// ==================== Theme ====================
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var btn = document.getElementById('btn-theme-toggle');
    btn.textContent = theme === 'dark' ? '🌙' : '☀️';
    btn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
}

async function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme') || 'dark';
    var next = current === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    await pyApi().set_theme(next);
}

// ==================== Settings Modal ====================
function openSettings() {
    document.getElementById('modal-settings').classList.remove('hidden');
    pyApi().get_api_key().then(function (key) {
        document.getElementById('api-key-input').value = key || '';
    });
    pyApi().get_github_token().then(function (token) {
        document.getElementById('github-token-input').value = token || '';
    });
}

function closeSettings() {
    document.getElementById('modal-settings').classList.add('hidden');
}

async function saveSettings() {
    var apiKey = document.getElementById('api-key-input').value.trim();
    var ghToken = document.getElementById('github-token-input').value.trim();
    await pyApi().set_api_key(apiKey);
    await pyApi().set_github_token(ghToken);
    toggleApiWarning(!apiKey);
    closeSettings();
}

function togglePasswordField(inputId, btn) {
    var input = document.getElementById(inputId);
    if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = '🔒';
    } else {
        input.type = 'password';
        btn.textContent = '👁';
    }
}

function toggleApiWarning(show) {
    var banner = document.getElementById('api-warning');
    if (show) {
        banner.classList.remove('hidden');
    } else {
        banner.classList.add('hidden');
    }
}

// ==================== Confirm Dialog ====================
var _confirmCallback = null;

function showConfirm(title, message, icon, onConfirm) {
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    document.getElementById('confirm-icon').textContent = icon || '⚠️';
    _confirmCallback = onConfirm;
    document.getElementById('modal-confirm').classList.remove('hidden');
    document.getElementById('btn-confirm-ok').onclick = function () {
        hideConfirm();
        if (_confirmCallback) _confirmCallback();
    };
}

function hideConfirm() {
    document.getElementById('modal-confirm').classList.add('hidden');
    _confirmCallback = null;
}

// ==================== Folder Picker ====================
async function pickFolder() {
    var folder = await pyApi().pick_folder();
    if (folder) {
        document.getElementById('install-path').textContent = folder;
        await pyApi().set_install_path(folder);
    }
}

// ==================== Project List ====================
async function refreshProjectList() {
    try {
        var projects = await pyApi().get_projects();
        renderProjects(projects);
    } catch (e) {
        console.error('Error loading projects:', e);
    }
}

function renderProjects(projects) {
    var container = document.getElementById('project-list');

    if (!projects || projects.length === 0) {
        container.innerHTML = '<div class="empty-state">No projects installed yet</div>';
        return;
    }

    var html = '';
    for (var i = 0; i < projects.length; i++) {
        var p = projects[i];
        var desc = p.description ? escapeHtml(truncate(p.description, 80)) : '';
        var status = p.status || 'installed';
        var badgeClass = status === 'installed' ? 'badge-installed' :
                         status === 'partial' ? 'badge-partial' : 'badge-failed';
        var badgeText = status === 'installed' ? '✓ Installed' :
                        status === 'partial' ? '⚠ Partial' : '✕ Failed';
        var timeAgo = p.installed_at ? formatTimeAgo(p.installed_at) : '';
        var safeId = escapeHtml(p.id);

        html += '<div class="project-card" data-id="' + safeId + '" data-searchable="' + escapeHtml((p.name + ' ' + p.owner + ' ' + (p.description || '')).toLowerCase()) + '">';
        html += '  <div class="project-info">';
        html += '    <div class="project-name-row">';
        html += '      <div class="project-name">' + escapeHtml(p.name) + '</div>';
        html += '      <span class="project-status-badge ' + badgeClass + '">' + badgeText + '</span>';
        html += '    </div>';
        html += '    <div class="project-owner">' + escapeHtml(p.owner) + '/' + escapeHtml(p.name) + '</div>';
        if (timeAgo) {
            html += '    <div class="project-time">' + timeAgo + '</div>';
        }
        if (desc) {
            html += '    <div class="project-desc">' + desc + '</div>';
        }
        html += '  </div>';
        html += '  <div class="project-actions">';
        html += '    <button class="btn-launch" onclick="launchProject(\'' + safeId + '\')" aria-label="Launch ' + escapeHtml(p.name) + '">Launch</button>';
        html += '    <button class="btn-folder" onclick="openProjectFolder(\'' + safeId + '\')" aria-label="Open folder for ' + escapeHtml(p.name) + '">Open Folder</button>';
        html += '    <button class="btn-update" onclick="updateProject(\'' + safeId + '\')" aria-label="Pull latest changes for ' + escapeHtml(p.name) + '" title="git pull latest changes">↑ Update</button>';
        html += '  </div>';
        html += '  <button class="btn-remove" onclick="uninstallProject(\'' + safeId + '\')" title="Uninstall" aria-label="Uninstall ' + escapeHtml(p.name) + '">✕</button>';
        html += '</div>';
    }
    container.innerHTML = html;
}

function filterProjects() {
    var query = document.getElementById('search-input').value.toLowerCase().trim();
    var cards = document.querySelectorAll('.project-card');
    cards.forEach(function (card) {
        var searchable = card.getAttribute('data-searchable') || '';
        if (!query || searchable.indexOf(query) !== -1) {
            card.style.display = '';
        } else {
            card.style.display = 'none';
        }
    });
}

function launchProject(projectId) {
    pyApi().launch_project(projectId);
}

function openProjectFolder(projectId) {
    pyApi().open_folder(projectId);
}

function openCurrentProjectFolder() {
    if (currentProjectMeta && currentProjectMeta.project_id) {
        pyApi().open_folder(currentProjectMeta.project_id);
    }
}

function uninstallProject(projectId) {
    showConfirm(
        'Uninstall Project',
        'Delete files from disk too? Click Confirm to delete all files, or Cancel to only remove from list.',
        '🗑️',
        async function () {
            var result = await pyApi().uninstall_project(projectId, true);
            if (!result || !result.success) {
                alert('Uninstall failed: ' + (result && result.error ? result.error : 'Unknown error'));
            }
            await refreshProjectList();
        }
    );
    // Also wire a secondary "remove from list only" path via the cancel btn
    document.getElementById('btn-confirm-cancel').onclick = async function () {
        hideConfirm();
        await pyApi().uninstall_project(projectId, false);
        await refreshProjectList();
        // Re‑bind cancel for next use
        document.getElementById('btn-confirm-cancel').onclick = hideConfirm;
    };
}

function updateProject(projectId) {
    showConfirm(
        'Update Project',
        'Run git pull to get the latest changes?',
        '↑',
        function () {
            pyApi().update_project(projectId);
        }
    );
}

// ==================== Install Button State ====================
function setInstallBtnLoading(loading) {
    var btn = document.getElementById('btn-install');
    if (loading) {
        btn.disabled = true;
        btn.textContent = 'Analyzing…';
        btn.classList.add('btn-loading');
    } else {
        btn.disabled = false;
        btn.textContent = 'Install';
        btn.classList.remove('btn-loading');
    }
}

function resetInstallBtn() {
    setInstallBtnLoading(false);
}

// ==================== Analyze Flow (Stage 1) ====================
async function startAnalyze() {
    var urlInput = document.getElementById('repo-url');
    var url = urlInput.value.trim();
    var errorEl = document.getElementById('url-error');

    if (!url) {
        errorEl.textContent = 'Please enter a GitHub repository URL';
        return;
    }

    var validation;
    try {
        validation = await pyApi().validate_github_url(url);
    } catch (e) {
        errorEl.textContent = 'Error validating URL';
        return;
    }

    if (!validation.valid) {
        errorEl.textContent = 'Please enter a valid GitHub URL or owner/repo';
        return;
    }

    var apiKey = await pyApi().get_api_key();
    if (!apiKey) {
        errorEl.textContent = 'OpenRouter API key not set. Please add it in Settings.';
        return;
    }

    errorEl.textContent = '';
    currentRepoUrl = url;

    resetInstallUI();
    setInstallBtnLoading(true);

    document.getElementById('analyzing-repo-name').textContent = validation.owner + '/' + validation.repo;
    document.getElementById('installing-repo-name').textContent = validation.repo;
    document.getElementById('done-repo-name').textContent = validation.repo;
    document.getElementById('btn-done-launch').textContent = 'Launch ' + validation.repo;

    showScreen('screen-analyzing', 'left');
    showAnalyzingContent(true);

    pyApi().start_analyze(url);
}

function resetInstallUI() {
    document.getElementById('terminal').innerHTML = '';
    document.getElementById('step-list').innerHTML = '';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-bar').closest('.progress-bar-wrapper').setAttribute('aria-valuenow', '0');
    document.getElementById('install-error-banner').className = 'install-error-banner';
    document.getElementById('done-notes').classList.add('hidden');
    document.getElementById('plan-cache-status').classList.add('hidden');
    document.getElementById('plan-cache-status').textContent = '';

    document.getElementById('webui-offer').classList.add('hidden');
    document.getElementById('webui-building').classList.add('hidden');
    document.getElementById('webui-done').classList.add('hidden');

    stepsCompleted = 0;
    totalSteps = 0;
    failedStepId = null;
    currentInstallPlan = null;
    currentProjectMeta = null;
    isInstalling = false;
    pinTerminal();
}

function resetState() {
    resetInstallUI();
    resetInstallBtn();
    document.getElementById('repo-url').value = '';
    document.getElementById('url-error').textContent = '';
}

function showAnalyzingContent(show) {
    var content = document.getElementById('analyzing-content');
    var error = document.getElementById('analyzing-error');
    if (show) {
        content.style.display = '';
        error.classList.remove('visible');
    } else {
        content.style.display = 'none';
        error.classList.add('visible');
    }
}

// ==================== Plan Review (Stage 1.5) ====================
function showPlanReview(data) {
    var plan = data.plan;

    document.getElementById('plan-repo-name').textContent = data.owner + '/' + data.repo;
    document.getElementById('plan-project-type').textContent = plan.project_type || 'unknown';
    document.getElementById('plan-entry-point').textContent = plan.entry_point || 'N/A';
    document.getElementById('plan-size').textContent = data.size_mb ? data.size_mb + ' MB (repo only)' : 'Unknown';
    document.getElementById('plan-stars').textContent = data.stars ? '⭐ ' + formatNumber(data.stars) : 'N/A';

    var cacheEl = document.getElementById('plan-cache-status');
    if (data.has_cached) {
        var cacheText = 'Using cached plan';
        if (data.cached_at) {
            cacheText += ' from ' + formatAbsoluteDate(data.cached_at);
        }
        cacheEl.textContent = cacheText + '. Re-analyze by deleting the cache entry in data/plans/.';
        cacheEl.classList.remove('hidden');
    } else {
        cacheEl.classList.add('hidden');
        cacheEl.textContent = '';
    }

    // Render steps
    var stepList = document.getElementById('plan-step-list');
    var html = '';
    if (plan.steps) {
        for (var i = 0; i < plan.steps.length; i++) {
            var step = plan.steps[i];
            html += '<div class="plan-step-item">';
            html += '  <div class="plan-step-num">' + step.id + '</div>';
            html += '  <div class="plan-step-info">';
            html += '    <div class="plan-step-desc">' + escapeHtml(step.description) + '</div>';
            if (step.command) {
                html += '    <div class="plan-step-cmd">' + escapeHtml(step.command) + '</div>';
            }
            html += '  </div>';
            html += '</div>';
        }
    }
    stepList.innerHTML = html;

    // Show notes
    var notesEl = document.getElementById('plan-notes');
    if (plan.notes) {
        notesEl.textContent = plan.notes;
        notesEl.classList.remove('hidden');
    } else {
        notesEl.classList.add('hidden');
    }

    showScreen('screen-plan-review', 'left');
}

async function approveInstall() {
    var installPath = document.getElementById('install-path').textContent;
    showScreen('screen-installing', 'left');
    await pyApi().approve_and_install(installPath);
}

// ==================== Cancel ====================
async function cancelInstall() {
    await pyApi().cancel_install();
}

// ==================== Terminal ====================
function pinTerminal() {
    terminalPinned = true;
    document.getElementById('btn-scroll-bottom').classList.add('hidden');
}

function unpinTerminal() {
    terminalPinned = false;
    document.getElementById('btn-scroll-bottom').classList.remove('hidden');
}

function scrollTerminalToBottom() {
    var terminal = document.getElementById('terminal');
    terminal.scrollTop = terminal.scrollHeight;
}

function toggleTerminal() {
    var wrapper = document.querySelector('.terminal-wrapper');
    terminalCollapsed = !terminalCollapsed;
    if (terminalCollapsed) {
        wrapper.classList.add('terminal-collapsed');
    } else {
        wrapper.classList.remove('terminal-collapsed');
    }
}

function copyLog() {
    var terminal = document.getElementById('terminal');
    var text = terminal.innerText || terminal.textContent;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function () {
            var btn = document.getElementById('btn-copy-log');
            btn.textContent = '✓ Copied';
            setTimeout(function () { btn.textContent = '📋 Copy'; }, 2000);
        });
    }
}

// ==================== Retry / Skip ====================
function retryStep() {
    if (failedStepId === null) return;
    document.getElementById('install-error-banner').className = 'install-error-banner';
    var installPath = document.getElementById('install-path').textContent;
    pyApi().retry_from_step(failedStepId, installPath);
}

function skipStep() {
    if (failedStepId === null) return;
    document.getElementById('install-error-banner').className = 'install-error-banner';
    var installPath = document.getElementById('install-path').textContent;
    pyApi().skip_and_continue(failedStepId, installPath);
}

// ==================== Install Event Handler ====================
window.onInstallEvent = function (eventJson) {
    var event;
    try {
        event = JSON.parse(eventJson);
    } catch (e) {
        console.error('Failed to parse event:', eventJson, e);
        return;
    }

    switch (event.type) {
        case 'stage':
            handleStageEvent(event);
            break;
        case 'plan_review':
            handlePlanReview(event);
            break;
        case 'plan':
            handlePlanEvent(event);
            break;
        case 'step_start':
            handleStepStart(event);
            break;
        case 'output':
            handleOutput(event);
            break;
        case 'step_done':
            handleStepDone(event);
            break;
        case 'step_error':
            handleStepError(event);
            break;
        case 'done':
            handleDone(event);
            break;
        case 'webui_building':
            handleWebuiBuilding();
            break;
        case 'webui_done':
            handleWebuiDone(event);
            break;
        case 'update_start':
            handleUpdateStart(event);
            break;
        case 'update_output':
            // Could be shown in a dedicated modal, for now just log
            console.log('[update]', event.line);
            break;
        case 'update_done':
            handleUpdateDone(event);
            break;
    }
};

function handleStageEvent(event) {
    switch (event.stage) {
        case 'fetching':
            document.getElementById('analyzing-subtitle').textContent =
                'Fetching README and project files...';
            break;
        case 'analyzing':
            document.getElementById('analyzing-subtitle').textContent =
                'Reading documentation with AI...';
            break;
        case 'installing':
            isInstalling = true;
            resetInstallBtn();
            showScreen('screen-installing', 'left');
            break;
        case 'done':
            isInstalling = false;
            showScreen('screen-done', 'left');
            break;
        case 'cancelled':
            isInstalling = false;
            resetInstallBtn();
            showScreen('screen-cancelled');
            break;
        case 'error':
            isInstalling = false;
            resetInstallBtn();
            handleErrorStage(event.message || 'An unknown error occurred.');
            break;
    }
}

function handlePlanReview(event) {
    currentInstallPlan = event.plan;
    resetInstallBtn();
    showPlanReview(event);
}

function handleErrorStage(message) {
    var analyzingScreen = document.getElementById('screen-analyzing');
    if (analyzingScreen.classList.contains('active')) {
        showAnalyzingContent(false);
        document.getElementById('analyzing-error-msg').textContent = message;
        return;
    }

    var banner = document.getElementById('install-error-banner');
    document.getElementById('install-error-msg').textContent = message;
    banner.classList.add('visible');
}

function handlePlanEvent(event) {
    currentInstallPlan = event.plan;
    totalSteps = event.plan.steps ? event.plan.steps.length : 0;
    stepsCompleted = 0;

    var stepList = document.getElementById('step-list');
    var html = '';
    for (var i = 0; i < event.plan.steps.length; i++) {
        var step = event.plan.steps[i];
        html += '<div class="step-item" id="step-' + step.id + '" data-id="' + step.id + '">';
        html += '  <div class="step-icon">⏳</div>';
        html += '  <div class="step-desc">' + escapeHtml(step.description) + '</div>';
        html += '</div>';
    }
    stepList.innerHTML = html;
}

function handleStepStart(event) {
    var stepEl = document.getElementById('step-' + event.step_id);
    if (stepEl) {
        stepEl.classList.add('active');
        stepEl.classList.remove('done', 'failed');
        var icon = stepEl.querySelector('.step-icon');
        icon.textContent = '🔄';
        icon.classList.add('running');
    }

    // Build step list on-the-fly if not already built (for retry)
    if (!stepEl && currentInstallPlan) {
        var stepList = document.getElementById('step-list');
        var div = document.createElement('div');
        div.className = 'step-item active';
        div.id = 'step-' + event.step_id;
        div.setAttribute('data-id', event.step_id);
        div.innerHTML = '<div class="step-icon running">🔄</div><div class="step-desc">' + escapeHtml(event.description) + '</div>';
        stepList.appendChild(div);
    }
}

function handleOutput(event) {
    var terminal = document.getElementById('terminal');
    var line = document.createElement('div');
    line.className = 'terminal-line';

    var text = event.line || '';
    if (text.startsWith('$ ')) {
        line.classList.add('command');
    } else if (text.toLowerCase().indexOf('warning') !== -1) {
        line.classList.add('warning');
    } else if (text.toLowerCase().indexOf('error') !== -1 && !text.startsWith('$')) {
        line.classList.add('error');
    }

    line.textContent = text;
    terminal.appendChild(line);

    // Only auto-scroll if pinned
    if (terminalPinned) {
        terminal.scrollTop = terminal.scrollHeight;
    }
}

function handleStepDone(event) {
    if (!event.success) {
        return;
    }

    var stepEl = document.getElementById('step-' + event.step_id);
    if (stepEl) {
        stepEl.classList.remove('active');
        stepEl.classList.add('done');
        var icon = stepEl.querySelector('.step-icon');
        icon.textContent = '✅';
        icon.classList.remove('running');
    }

    failedStepId = null;
    stepsCompleted++;
    updateProgressBar();
}

function handleStepError(event) {
    var stepEl = document.getElementById('step-' + event.step_id);
    if (stepEl) {
        stepEl.classList.remove('active');
        stepEl.classList.add('failed');
        var icon = stepEl.querySelector('.step-icon');
        icon.textContent = '❌';
        icon.classList.remove('running');
    }

    failedStepId = event.step_id;

    if (event.error) {
        var terminal = document.getElementById('terminal');
        var line = document.createElement('div');
        line.className = 'terminal-line error';
        line.textContent = 'ERROR: ' + event.error;
        terminal.appendChild(line);
        // Always scroll on errors so user sees them
        terminal.scrollTop = terminal.scrollHeight;
    }

    stepsCompleted++;
    updateProgressBar();

    // Show error banner with retry/skip
    var banner = document.getElementById('install-error-banner');
    document.getElementById('install-error-msg').textContent = 'Step failed: ' + (event.error || 'Unknown error').substring(0, 200);
    banner.classList.add('visible');
}

function handleDone(event) {
    currentProjectMeta = event;

    document.getElementById('done-path').textContent = event.project_dir || '';

    var notesEl = document.getElementById('done-notes');
    if (event.notes) {
        notesEl.textContent = event.notes;
        notesEl.classList.remove('hidden');
    } else {
        notesEl.classList.add('hidden');
    }

    if (event.needs_webui) {
        document.getElementById('webui-offer').classList.remove('hidden');
    }
}

function handleWebuiBuilding() {
    document.getElementById('webui-offer').classList.add('hidden');
    document.getElementById('webui-building').classList.remove('hidden');
}

function handleWebuiDone(event) {
    document.getElementById('webui-building').classList.add('hidden');
    if (event.success) {
        document.getElementById('webui-done').classList.remove('hidden');
    }
}

function handleUpdateStart(event) {
    console.log('Updating project:', event.project_id);
}

function handleUpdateDone(event) {
    if (event.success) {
        showToast('✓ Updated ' + event.project_id + ' successfully');
    } else {
        showToast('✕ Update failed: ' + (event.error || 'Unknown error'), true);
    }
    refreshProjectList();
}

// ==================== Toast Notification ====================
function showToast(message, isError) {
    var existing = document.getElementById('gi-toast');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.id = 'gi-toast';
    toast.className = 'gi-toast' + (isError ? ' gi-toast-error' : '');
    toast.textContent = message;
    toast.setAttribute('role', 'status');
    document.body.appendChild(toast);

    // Trigger animation then remove
    requestAnimationFrame(function () {
        toast.classList.add('gi-toast-visible');
    });
    setTimeout(function () {
        toast.classList.remove('gi-toast-visible');
        setTimeout(function () { toast.remove(); }, 300);
    }, 3000);
}

// ==================== Progress Bar ====================
function updateProgressBar() {
    if (totalSteps === 0) return;
    var pct = Math.round((stepsCompleted / totalSteps) * 100);
    var bar = document.getElementById('progress-bar');
    bar.style.width = pct + '%';
    bar.closest('.progress-bar-wrapper').setAttribute('aria-valuenow', String(pct));
}

// ==================== Helpers ====================
function formatAbsoluteDate(isoString) {
    try {
        var date = new Date(isoString);
        return date.toLocaleString();
    } catch (e) {
        return isoString;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.substring(0, max) + '...' : str;
}

function formatTimeAgo(isoString) {
    try {
        var date = new Date(isoString);
        var now = new Date();
        var diffMs = now - date;
        var diffMins = Math.floor(diffMs / 60000);
        var diffHours = Math.floor(diffMs / 3600000);
        var diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return diffMins + 'm ago';
        if (diffHours < 24) return diffHours + 'h ago';
        if (diffDays < 30) return diffDays + 'd ago';
        return date.toLocaleDateString();
    } catch (e) {
        return '';
    }
}

function formatNumber(num) {
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'k';
    }
    return String(num);
}
