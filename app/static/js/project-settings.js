let settingsOpener = null;
let settingsLoadId = 0;

function closeSystemSettingsModal() {
    settingsLoadId += 1;
    document.getElementById('system-settings-modal').style.display = 'none';
    settingsOpener?.focus();
}

function showSettingsError(message) {
    const error = document.getElementById('system-settings-error');
    error.textContent = message;
    error.hidden = !message;
}

async function openSystemSettingsModal() {
    settingsOpener = document.activeElement;
    const loadId = ++settingsLoadId;
    const save = document.getElementById('system-settings-save');
    const input = document.getElementById('default-project-location');
    document.getElementById('system-settings-modal').style.display = 'flex';
    input.value = '';
    input.disabled = true;
    save.disabled = true;
    showSettingsError('');
    try {
        const response = await fetch('/api/settings');
        const result = await response.json();
        if (!result.success) throw new Error(result.error);
        if (loadId !== settingsLoadId) return;
        input.value = result.data.default_project_location;
        input.placeholder = result.data.project_location || '留空使用上次成功创建的位置';
        input.disabled = false;
        save.disabled = false;
        input.focus();
    } catch (error) {
        if (loadId === settingsLoadId) showSettingsError(error.message || '读取设置失败');
    }
}

document.addEventListener('click', async (event) => {
    const action = event.target.closest('[data-settings-action]')?.dataset.settingsAction;
    if (action === 'open') openSystemSettingsModal();
    if (action === 'close') closeSystemSettingsModal();
    if (action === 'browse') {
        const input = document.getElementById('default-project-location');
        if (input.disabled) return;
        const loadId = settingsLoadId;
        const path = await browseFolder();
        if (path && loadId === settingsLoadId) input.value = path;
    }
});

document.getElementById('system-settings-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const save = document.getElementById('system-settings-save');
    if (save.disabled) return;
    const loadId = settingsLoadId;
    save.disabled = true;
    showSettingsError('');
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                default_project_location: document.getElementById('default-project-location').value.trim()
            })
        });
        const result = await response.json();
        if (!result.success) throw new Error(result.error);
        if (loadId !== settingsLoadId) return;
        if (document.getElementById('create-project-modal').style.display === 'flex') {
            document.getElementById('new-project-location').value = result.data.project_location || '';
        }
        closeSystemSettingsModal();
        window.projectLibrary?.refreshLocation();
        showNotification('设置已保存');
    } catch (error) {
        if (loadId === settingsLoadId) showSettingsError(error.message || '保存设置失败');
    } finally {
        if (loadId === settingsLoadId) save.disabled = false;
    }
});
