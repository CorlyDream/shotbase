(() => {
    'use strict';

    const section = document.getElementById('project-covers');
    const list = document.getElementById('project-cover-list');
    const input = document.getElementById('project-cover-files');
    const upload = document.getElementById('project-cover-upload');
    const previous = document.getElementById('project-cover-previous');
    const next = document.getElementById('project-cover-next');
    const status = document.getElementById('project-cover-status');
    const errorBox = document.getElementById('project-cover-error');
    const dialog = document.getElementById('project-cover-preview');
    const ratios = ['4:3', '3:4', '16:9', '9:16', '其他'];
    let projectPath = null;
    let epoch = 0;
    let covers = [];
    let busy = false;
    let previewIndex = 0;
    let previewId = null;

    function icon(name) {
        const span = document.createElement('span');
        span.className = 'project-cover-icon project-cover-icon-' + name;
        span.setAttribute('aria-hidden', 'true');
        return span;
    }

    function isCurrent(session) {
        return session.epoch === epoch && session.path === projectPath;
    }

    function setError(message) {
        document.getElementById('project-cover-error-text').textContent = message;
        errorBox.hidden = !message;
    }

    function updateArrows() {
        previous.disabled = list.scrollLeft <= 1;
        next.disabled = list.scrollWidth - list.clientWidth - list.scrollLeft <= 2;
    }

    function setBusy(value, message = '') {
        busy = value;
        upload.disabled = value;
        input.disabled = value;
        list.setAttribute('aria-busy', String(value));
        status.textContent = message;
        status.hidden = !message;
        list.querySelectorAll('[data-cover-action="delete"], .project-cover-empty').forEach(button => {
            button.disabled = value;
        });
    }

    function render() {
        const position = list.scrollLeft;
        const grouped = ratios.map(ratio => ({ratio, items: covers.filter(cover => (cover.ratio || '其他') === ratio)}));
        covers = grouped.flatMap(group => group.items);
        const tiles = covers.map((cover, index) => {
            const item = document.createElement('div');
            item.className = 'project-cover-item';
            item.setAttribute('role', 'listitem');
            const preview = document.createElement('button');
            preview.type = 'button';
            preview.className = 'project-cover-preview-button';
            preview.dataset.coverAction = 'preview';
            preview.dataset.index = String(index);
            preview.title = '预览封面 ' + cover.name;
            preview.setAttribute('aria-label', preview.title);
            const image = document.createElement('img');
            image.className = 'project-cover-image';
            image.src = cover.url;
            image.alt = cover.name;
            image.decoding = 'async';
            image.loading = 'lazy';
            image.addEventListener('error', () => {
                preview.title = '封面图片读取失败：' + cover.name;
                image.alt = preview.title;
            });
            preview.append(image);
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'project-cover-control project-cover-delete';
            remove.dataset.coverAction = 'delete';
            remove.dataset.id = cover.id;
            remove.title = '删除封面 ' + cover.name;
            remove.setAttribute('aria-label', remove.title);
            remove.disabled = busy;
            remove.append(icon('x'));
            const name = document.createElement('span');
            name.className = 'project-cover-name';
            name.textContent = cover.name;
            name.title = cover.name;
            item.append(preview, remove, name);
            return item;
        });
        const nodes = [];
        let offset = 0;
        for (const group of grouped) {
            if (!group.items.length) continue;
            const container = document.createElement('section');
            container.className = 'project-cover-group';
            container.dataset.ratio = group.ratio;
            container.setAttribute('aria-label', group.ratio + ' 封面');
            const shape = group.ratio === '其他' ? 1 : group.ratio.split(':').reduce((width, height) => width / height);
            container.style.setProperty('--cover-ratio', String(shape));
            const heading = document.createElement('div');
            heading.className = 'project-cover-group-head';
            const title = document.createElement('h4');
            title.className = 'project-cover-group-title';
            title.textContent = group.ratio;
            const count = document.createElement('span');
            count.className = 'project-cover-count';
            count.textContent = group.items.length + ' 张';
            heading.append(title, count);
            const row = document.createElement('div');
            row.className = 'project-cover-group-items';
            row.setAttribute('role', 'list');
            row.append(...tiles.slice(offset, offset + group.items.length));
            offset += group.items.length;
            container.append(heading, row);
            nodes.push(container);
        }
        if (!covers.length) {
            const empty = document.createElement('button');
            empty.type = 'button';
            empty.className = 'project-cover-empty';
            empty.dataset.coverAction = 'upload';
            empty.disabled = busy;
            empty.append(icon('plus'), document.createTextNode('上传封面'));
            nodes.push(empty);
        }
        list.replaceChildren(...nodes);
        list.scrollLeft = position;
        const count = document.getElementById('project-cover-count');
        count.textContent = covers.length + ' 张';
        count.hidden = !covers.length;
        updateArrows();
        if (dialog.open) {
            const selected = covers.findIndex(cover => cover.id === previewId);
            if (selected < 0) closePreview();
            else showPreview(selected);
        }
    }

    function closePreview() {
        if (dialog.open) dialog.close();
    }

    function showPreview(index) {
        if (!covers.length) return;
        previewIndex = Math.max(0, Math.min(index, covers.length - 1));
        const cover = covers[previewIndex];
        previewId = cover.id;
        const image = document.getElementById('project-cover-preview-image');
        image.src = cover.url;
        image.alt = cover.name;
        document.getElementById('project-cover-preview-name').textContent = cover.name;
        document.getElementById('project-cover-preview-previous').disabled = previewIndex === 0;
        document.getElementById('project-cover-preview-next').disabled = previewIndex === covers.length - 1;
        if (!dialog.open) dialog.showModal();
    }

    function reset() {
        epoch += 1;
        projectPath = null;
        covers = [];
        input.value = '';
        list.scrollLeft = 0;
        closePreview();
        setError('');
        setBusy(false);
        render();
    }

    async function refresh() {
        if (!projectPath || busy) return;
        const session = {epoch, path: projectPath};
        setError('');
        setBusy(true, '正在读取封面…');
        try {
            const response = await fetch('/api/project/covers?' + new URLSearchParams({project_path: session.path}));
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || '读取封面失败');
            if (!isCurrent(session)) return;
            if (result.data.project_path !== session.path) throw new Error('项目已切换，请重新读取封面');
            covers = result.data.covers;
            render();
        } catch (error) {
            if (isCurrent(session)) setError(error.message || '读取封面失败');
        } finally {
            if (isCurrent(session)) setBusy(false);
        }
    }

    async function mutate(options, message) {
        if (!projectPath || busy) return;
        const session = {epoch, path: projectPath};
        setError('');
        setBusy(true, message);
        try {
            const response = await fetch(options.url, options);
            const result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || '封面保存失败');
            if (!isCurrent(session)) return;
            if (result.data.project_path !== session.path) throw new Error('项目已切换，请重新读取封面');
            covers = result.data.covers;
            render();
        } catch (error) {
            if (isCurrent(session)) setError(error.message || '封面保存失败');
        } finally {
            if (isCurrent(session)) setBusy(false);
        }
    }

    input.addEventListener('change', () => {
        const files = Array.from(input.files);
        input.value = '';
        if (!files.length || !projectPath || busy) return;
        const form = new FormData();
        form.append('project_path', projectPath);
        for (const file of files) form.append('files', file);
        mutate({url: '/api/project/covers', method: 'POST', body: form}, `正在上传 ${files.length} 张封面…`);
    });

    section.addEventListener('click', event => {
        const button = event.target.closest('[data-cover-action]');
        if (!button || button.disabled) return;
        const action = button.dataset.coverAction;
        if (action === 'upload' && !busy) input.click();
        if (action === 'retry') refresh();
        if (action === 'preview') showPreview(Number(button.dataset.index));
        if (action === 'previous' || action === 'next') {
            const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            list.scrollBy({left: (action === 'next' ? 1 : -1) * list.clientWidth * .8,
                           behavior: reducedMotion ? 'instant' : 'smooth'});
        }
        if (action === 'delete' && !busy) {
            const cover = covers.find(item => item.id === button.dataset.id);
            if (!cover || !window.confirm(`删除封面“${cover.name}”？`)) return;
            mutate({url: '/api/project/covers/' + encodeURIComponent(cover.id), method: 'DELETE',
                    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({project_path: projectPath})},
                   '正在删除封面…');
        }
    });

    dialog.addEventListener('click', event => {
        const action = event.target.closest('[data-cover-preview-action]')?.dataset.coverPreviewAction;
        if (action === 'close') closePreview();
        if (action === 'previous') showPreview(previewIndex - 1);
        if (action === 'next') showPreview(previewIndex + 1);
        if (event.target === dialog) {
            const box = dialog.getBoundingClientRect();
            if (event.clientX < box.left || event.clientX > box.right ||
                    event.clientY < box.top || event.clientY > box.bottom) closePreview();
        }
    });
    dialog.addEventListener('close', () => {
        if (dialog.open) return;
        previewId = null;
        document.getElementById('project-cover-preview-image').removeAttribute('src');
    });
    dialog.addEventListener('keydown', event => {
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            event.preventDefault();
            event.stopPropagation();
            showPreview(previewIndex + (event.key === 'ArrowRight' ? 1 : -1));
        }
    });
    list.addEventListener('scroll', updateArrows, {passive: true});
    new ResizeObserver(updateArrows).observe(list);
    window.projectCovers = {
        open(path) {
            reset();
            projectPath = path;
            refresh();
        },
        reset
    };
})();
