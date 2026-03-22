/**
 * GitInstaller — app.js
 * Frontend logic, screen transitions, API bridge calls
 */

// ==================== State ====================
let currentInstallPlan = null;
let currentProjectMeta = null;
let currentRepoUrl = '';
let stepsCompleted = 0;
let totalSteps = 0;

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
    document.getElementById('btn-save-key').addEventListener('click', saveApiKey);
    document.getElementById('btn-toggle-password').addEventListener('click', togglePasswordVisibility);

    // Folder picker
    document.getElementById('btn-change-folder').addEventListener('click', pickFolder);

    // Install
    document.getElementById('btn-install').addEventListener('click', startInstall);

    // URL input — clear error on type
    document.getElementById('repo-url').addEventListener('input', function () {
        document.getElementById('url-error').textContent = '';
    });

    // Enter key on URL input
    document.getElementById('repo-url').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') startInstall();
    });

    // Error go back
    document.getElementById('btn-error-back').addEventListener('click', function () {
        showScreen('screen-home');
    });

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
    document.getElementById('done-path').addEventListener('click', function () {
        if (currentProjectMeta && currentProjectMeta.project_id) {
            pyApi().open_folder(currentProjectMeta.project_id);
        }
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
}

// ==================== Screen Navigation ====================
function showScreen(screenId) {
    const screens = document.querySelectorAll('.screen');
    screens.forEach(function (s) {
        s.classList.add('hidden');
    });
    const target = document.getElementById(screenId);
    if (target) {
        target.classList.remove('hidden');
    }
}

// ==================== Settings Modal ====================
function openSettings() {
    document.getElementById('modal-settings').classList.remove('hidden');
    pyApi().get_api_key().then(function (key) {
        document.getElementById('api-key-input').value = key || '';
    });
}

function closeSettings() {
    document.getElementById('modal-settings').classList.add('hidden');
}

async function saveApiKey() {
    const input = document.getElementById('api-key-input');
    const key = input.value.trim();
    await pyApi().set_api_key(key);
    toggleApiWarning(!key);
    closeSettings();
}

function togglePasswordVisibility() {
    const input = document.getElementById('api-key-input');
    const btn = document.getElementById('btn-toggle-password');
    if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = '🔒';
    } else {
        input.type = 'password';
        btn.textContent = '👁';
    }
}

function toggleApiWarning(show) {
    const banner = document.getElementById('api-warning');
    if (show) {
        banner.classList.remove('hidden');
    } else {
        banner.classList.add('hidden');
    }
}

// ==================== Folder Picker ====================
async function pickFolder() {
    const folder = await pyApi().pick_folder();
    if (folder) {
        document.getElementById('install-path').textContent = folder;
        await pyApi().set_install_path(folder);
    }
}

// ==================== Project List ====================
async function refreshProjectList() {
    try {
        const projects = await pyApi().get_projects();
        const container = document.getElementById('project-list');

        if (!projects || projects.length === 0) {
            container.innerHTML = '<div class="empty-state">No projects installed yet</div>';
            return;
        }

        let html = '';
        for (const p of projects) {
            const desc = p.description ? escapeHtml(truncate(p.description, 80)) : '';
            html += `
                <div class="project-card" data-id="${escapeHtml(p.id)}">
                    <div class="project-info">
                        <div class="project-name">${escapeHtml(p.name)}</div>
                        <div class="project-owner">${escapeHtml(p.owner)}/${escapeHtml(p.name)}</div>
                        ${desc ? `<div class="project-desc">${desc}</div>` : ''}
                    </div>
                    <div class="project-actions">
                        <button class="btn-launch" onclick="launchProject('${escapeHtml(p.id)}')">Launch</button>
                        <button class="btn-folder" onclick="openProjectFolder('${escapeHtml(p.id)}')">Open Folder</button>
                    </div>
                    <button class="btn-remove" onclick="removeProject('${escapeHtml(p.id)}')" title="Remove">✕</button>
                </div>
            `;
        }
        container.innerHTML = html;
    } catch (e) {
        console.error('Error loading projects:', e);
    }
}

function launchProject(projectId) {
    pyApi().launch_project(projectId);
}

function openProjectFolder(projectId) {
    pyApi().open_folder(projectId);
}

async function removeProject(projectId) {
    if (!confirm('Remove this project from the list? (Files will not be deleted)')) return;
    await pyApi().remove_project(projectId);
    await refreshProjectList();
}

// ==================== Install Flow ====================
async function startInstall() {
    const urlInput = document.getElementById('repo-url');
    const url = urlInput.value.trim();
    const errorEl = document.getElementById('url-error');

    if (!url) {
        errorEl.textContent = 'Please enter a GitHub repository URL';
        return;
    }

    let validation;
    try {
        validation = await pyApi().validate_github_url(url);
    } catch (e) {
        errorEl.textContent = 'Error validating URL';
        return;
    }

    if (!validation.valid) {
        errorEl.textContent = 'Please enter a valid GitHub repository URL';
        return;
    }

    const apiKey = await pyApi().get_api_key();
    if (!apiKey) {
        errorEl.textContent = 'OpenRouter API key not set. Please add it in Settings.';
        return;
    }

    errorEl.textContent = '';
    currentRepoUrl = url;

    resetInstallUI();

    document.getElementById('analyzing-repo-name').textContent = `${validation.owner}/${validation.repo}`;
    document.getElementById('installing-repo-name').textContent = validation.repo;
    document.getElementById('done-repo-name').textContent = validation.repo;
    document.getElementById('btn-done-launch').textContent = `Launch ${validation.repo}`;

    showScreen('screen-analyzing');
    showAnalyzingContent(true);

    const installPath = document.getElementById('install-path').textContent;
    pyApi().start_install(url, installPath);
}

function resetInstallUI() {
    document.getElementById('terminal').innerHTML = '';
    document.getElementById('step-list').innerHTML = '';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('install-error-banner').className = 'install-error-banner';
    document.getElementById('done-notes').classList.add('hidden');

    // Reset WebUI state
    document.getElementById('webui-offer').classList.add('hidden');
    document.getElementById('webui-building').classList.add('hidden');
    document.getElementById('webui-done').classList.add('hidden');

    stepsCompleted = 0;
    totalSteps = 0;
    currentInstallPlan = null;
    currentProjectMeta = null;
}

function resetState() {
    resetInstallUI();
    document.getElementById('repo-url').value = '';
    document.getElementById('url-error').textContent = '';
}

function showAnalyzingContent(show) {
    const content = document.getElementById('analyzing-content');
    const error = document.getElementById('analyzing-error');
    if (show) {
        content.style.display = '';
        error.classList.remove('visible');
    } else {
        content.style.display = 'none';
        error.classList.add('visible');
    }
}

// ==================== Install Event Handler ====================
window.onInstallEvent = function (eventJson) {
    let event;
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
            showScreen('screen-installing');
            break;
        case 'done':
            showScreen('screen-done');
            break;
        case 'error':
            handleErrorStage(event.message || 'An unknown error occurred.');
            break;
    }
}

function handleErrorStage(message) {
    const analyzingScreen = document.getElementById('screen-analyzing');
    if (!analyzingScreen.classList.contains('hidden')) {
        showAnalyzingContent(false);
        document.getElementById('analyzing-error-msg').textContent = message;
        return;
    }

    const banner = document.getElementById('install-error-banner');
    document.getElementById('install-error-msg').textContent = message;
    banner.classList.add('visible');
}

function handlePlanEvent(event) {
    currentInstallPlan = event.plan;
    totalSteps = event.plan.steps ? event.plan.steps.length : 0;
    stepsCompleted = 0;

    const stepList = document.getElementById('step-list');
    let html = '';
    for (const step of event.plan.steps) {
        html += `
            <div class="step-item" id="step-${step.id}" data-id="${step.id}">
                <div class="step-icon">⏳</div>
                <div class="step-desc">${escapeHtml(step.description)}</div>
            </div>
        `;
    }
    stepList.innerHTML = html;
}

function handleStepStart(event) {
    const stepEl = document.getElementById(`step-${event.step_id}`);
    if (stepEl) {
        stepEl.classList.add('active');
        stepEl.classList.remove('done', 'failed');
        const icon = stepEl.querySelector('.step-icon');
        icon.textContent = '🔄';
        icon.classList.add('running');
    }
}

function handleOutput(event) {
    const terminal = document.getElementById('terminal');
    const line = document.createElement('div');
    line.className = 'terminal-line';

    if (event.line && event.line.startsWith('$ ')) {
        line.classList.add('command');
    }

    line.textContent = event.line || '';
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
}

function handleStepDone(event) {
    const stepEl = document.getElementById(`step-${event.step_id}`);
    if (stepEl) {
        stepEl.classList.remove('active');
        stepEl.classList.add('done');
        const icon = stepEl.querySelector('.step-icon');
        icon.textContent = '✅';
        icon.classList.remove('running');
    }

    stepsCompleted++;
    updateProgressBar();
}

function handleStepError(event) {
    const stepEl = document.getElementById(`step-${event.step_id}`);
    if (stepEl) {
        stepEl.classList.remove('active');
        stepEl.classList.add('failed');
        const icon = stepEl.querySelector('.step-icon');
        icon.textContent = '❌';
        icon.classList.remove('running');
    }

    if (event.error) {
        const terminal = document.getElementById('terminal');
        const line = document.createElement('div');
        line.className = 'terminal-line error';
        line.textContent = `ERROR: ${event.error}`;
        terminal.appendChild(line);
        terminal.scrollTop = terminal.scrollHeight;
    }

    stepsCompleted++;
    updateProgressBar();
}

function handleDone(event) {
    currentProjectMeta = event;

    document.getElementById('done-path').textContent = event.project_dir || '';

    // Show notes if present
    const notesEl = document.getElementById('done-notes');
    if (event.notes) {
        notesEl.textContent = event.notes;
        notesEl.classList.remove('hidden');
    } else {
        notesEl.classList.add('hidden');
    }

    // Show WebUI offer if needed
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

function updateProgressBar() {
    if (totalSteps === 0) return;
    const pct = Math.round((stepsCompleted / totalSteps) * 100);
    document.getElementById('progress-bar').style.width = pct + '%';
}

// ==================== Helpers ====================
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.substring(0, max) + '...' : str;
}
