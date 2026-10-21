(() => {
    const list = document.getElementById('recent-projects-list');
    const status = document.getElementById('library-status');
    const retry = document.getElementById('library-retry');
    let requestId = 0;

    function icon(name) {
        const image = document.createElement('img');
        image.className = 'library-icon';
        image.src = `/static/icons/ui/${name}.svg`;
        image.alt = '';
        return image;
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function projectItem(project, index) {
        const button = element('button', 'library-project');
        button.type = 'button';
        button.setAttribute('aria-label', `打开项目 ${project.name}`);
        const preview = element('span', 'library-project-preview');
        const empty = element('span', 'library-preview-empty');
        empty.append(icon('film'), element('span', '', '暂无分镜画面'));
        preview.append(empty);
        if (project.preview_url) {
            const image = document.createElement('img');
            image.alt = `${project.name}的分镜预览`;
            image.loading = 'lazy';
            image.decoding = 'async';
            image.addEventListener('load', () => { empty.remove(); });
            image.addEventListener('error', () => { image.remove(); });
            image.src = project.preview_url;
            preview.prepend(image);
        }
        const info = element('span', 'library-project-info');
        if (index === 0) info.append(element('span', 'library-project-last', '上次打开'));
        info.append(element('span', 'library-project-name', project.name));
        const path = element('span', 'library-project-path', project.path);
        path.title = project.path;
        info.append(path);

        const meta = element('span', 'library-project-meta');
        meta.append(element('span', '', `${project.shot_count || 0} 个分镜`));
        const date = new Date(project.updated || project.created);
        if (!Number.isNaN(date.getTime())) {
            const time = element('time', '', `更新于 ${new Intl.DateTimeFormat('zh-CN', {
                year: 'numeric', month: '2-digit', day: '2-digit'
            }).format(date)}`);
            time.dateTime = date.toISOString();
            meta.append(time);
        }
        const arrow = element('span', 'library-project-arrow');
        arrow.append(icon('arrow-up-right'));
        button.append(preview, info, meta, arrow);
        button.addEventListener('click', async () => {
            button.disabled = true;
            try {
                await openRecentProject(project.path);
            } finally {
                button.disabled = false;
            }
        });
        return button;
    }

    async function refreshLocation() {
        const path = document.getElementById('library-location-path');
        try {
            const response = await fetch('/api/project/last-location');
            const result = await response.json();
            if (!result.success) throw new Error(result.error);
            path.textContent = result.data.path || '尚未设置';
            path.title = result.data.path || '';
        } catch {
            path.textContent = '读取保存位置失败';
        }
    }

    async function load() {
        const id = ++requestId;
        status.hidden = false;
        status.textContent = '正在读取项目…';
        retry.hidden = true;
        list.replaceChildren();
        list.setAttribute('aria-busy', 'true');
        refreshLocation();
        try {
            const response = await fetch('/api/project/recent');
            const result = await response.json();
            if (!result.success || !Array.isArray(result.data)) throw new Error('项目列表不可用');
            if (id !== requestId) return;
            list.replaceChildren(...result.data.map(projectItem));
            status.textContent = result.data.length ? '' : '还没有最近项目';
            status.hidden = result.data.length > 0;
        } catch {
            if (id !== requestId) return;
            status.textContent = '无法读取最近项目，请重新加载。';
            retry.hidden = false;
        } finally {
            if (id === requestId) list.setAttribute('aria-busy', 'false');
        }
    }

    document.addEventListener('click', (event) => {
        const action = event.target.closest('[data-library-action]')?.dataset.libraryAction;
        if (action === 'open') openProjectDialog();
        if (action === 'new') openCreateProjectModal();
        if (action === 'theme') document.getElementById('theme-toggle').click();
        if (action === 'manual') toggleManualPath();
        if (action === 'retry') load();
    });

    document.getElementById('manual-path-form').addEventListener('submit', (event) => {
        event.preventDefault();
        loadProjectFromManualPath();
    });

    window.projectLibrary = {load, refreshLocation};
})();
