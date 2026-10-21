/* Storyboard studio enhancements. Keeps the existing ShotBase upload/version APIs. */
(() => {
    "use strict";

    const LABELS = {
        first_image: "首帧画面",
        last_image: "尾帧画面",
        video: "生成视频",
        alt_video: "备用视频",
        audio: "声音素材"
    };
    const FILE_HINTS = {
        first_image: "点击上传首帧 · 支持拖放",
        last_image: "点击上传尾帧",
        video: "点击上传视频",
        alt_video: "点击上传备用视频",
        audio: "点击上传音频"
    };
    const ASSET_TYPES = Object.keys(LABELS);
    let gallery = null;
    let lastGalleryTrigger = null;
    const pendingPromotions = new Set();

    /** Identify the active project without assuming the setup screen has loaded one. */
    function studioProjectPath() {
        return typeof currentProject !== "undefined" && currentProject
            ? currentProject.path
            : null;
    }

    /** A completed async request may only update cards from its original project. */
    function isCurrentProject(session) {
        return session && session.projectPath === studioProjectPath();
    }

    /** Escape file/shot text when displaying it in HTML-generated labels. */
    function makeElement(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    /** Construct the original-resolution preview URL for an existing frame. */
    function fullResolutionImageUrl(shotName, assetType, version) {
        return "/api/shots/image/" + encodeURIComponent(shotName) + "/" +
            encodeURIComponent(assetType) + "?v=" + encodeURIComponent(String(version || 0));
    }

    /** Replace a small generated thumbnail with the actual stored image.
     *
     * ShotBase makes 240x180 thumbnails for navigation, but the studio displays
     * frame previews hundreds of pixels wide. This resolves the blur without
     * increasing thumbnail cache sizes or editing the source image.
     */
    function applyFullResolutionPreview(shotName, assetType, info, zone) {
        if (assetType !== "first_image" && assetType !== "last_image") return;
        if (!info || !info.file || !zone) return;

        const image = zone.querySelector("img.preview-thumbnail");
        if (!image) return;

        const fallbackThumbnail = image.getAttribute("src");
        const imageUrl = fullResolutionImageUrl(
            shotName, assetType, info.current_version || info.max_version
        );
        if (image.getAttribute("src") === imageUrl) return;

        image.onerror = () => {
            // Legacy projects may contain files that cannot be served by the
            // promoted-image endpoint; show the old thumbnail if possible.
            image.onerror = null;
            if (fallbackThumbnail && !fallbackThumbnail.includes("/api/shots/image/")) {
                image.src = fallbackThumbnail;
            }
        };
        image.loading = "lazy";
        image.decoding = "async";
        image.alt = LABELS[assetType] + "（原图清晰预览）";
        image.src = imageUrl;
    }

    /** Extend the existing asset drop zone without changing its direct-child position. */
    function decorateAsset(shot, assetType, markup) {
        const holder = document.createElement("div");
        holder.innerHTML = markup.trim();
        const zone = holder.firstElementChild;
        if (!zone) return markup;

        zone.classList.add("studio-asset", "studio-asset-" + assetType);
        zone.dataset.studioShot = shot.name;
        zone.dataset.studioType = assetType;

        const info = shot[assetType] || {};
        const maxVersion = info.max_version || 0;
        const header = makeElement("div", "studio-asset-label");
        header.appendChild(makeElement("span", "", LABELS[assetType]));
        const count = makeElement(
            "span", "studio-version-count",
            maxVersion ? "最高 v" + String(maxVersion).padStart(3, "0") : "未上传"
        );
        header.appendChild(count);
        zone.insertBefore(header, zone.firstChild);

        // In compact mode, the selected version is a clear header control.
        // The original version badge remains available in the comfortable view.
        if (assetType === "first_image" && maxVersion > 0) {
            const current = info.current_version || info.max_version;
            const versionControl = makeElement(
                "button", "studio-current-version",
                "v" + String(current).padStart(3, "0") + " ▾"
            );
            versionControl.type = "button";
            versionControl.dataset.studioAction = "versions";
            versionControl.title = "查看全部首帧版本";
            versionControl.setAttribute("aria-label", "查看首帧历史版本");
            header.appendChild(versionControl);
        }

        const caption = zone.querySelector(".asset-caption-input");
        if (caption) caption.placeholder = "素材备注（可选）";
        applyFullResolutionPreview(shot.name, assetType, info, zone);

        if (maxVersion > 0) {
            const badge = zone.querySelector(".version-badge");
            if (badge) {
                badge.title = "查看全部历史版本";
                badge.setAttribute("role", "button");
                badge.setAttribute("tabindex", "0");
                badge.setAttribute("aria-label", "查看" + LABELS[assetType] + "历史版本");
            }
            const actions = makeElement("div", "studio-asset-actions");
            const galleryButton = makeElement("button", "studio-action-link", "查看版本");
            galleryButton.type = "button";
            galleryButton.dataset.studioAction = "versions";
            actions.appendChild(galleryButton);

            // Compact first frame: footer tools remain discoverable while the
            // picture receives the full width. Comfortable mode keeps its
            // original overlay prompt and inline caption field.
            if (assetType === "first_image") {
                const promptAction = makeElement(
                    "button", "studio-action-link studio-first-action", "提示词"
                );
                promptAction.type = "button";
                promptAction.dataset.studioAction = "prompt";
                promptAction.title = "查看或编辑首帧提示词";

                const captionAction = makeElement(
                    "button", "studio-action-link studio-first-action", "备注"
                );
                captionAction.type = "button";
                captionAction.dataset.studioAction = "caption";
                captionAction.title = "编辑首帧素材备注";
                captionAction.setAttribute("aria-expanded", "false");

                actions.append(promptAction, captionAction);
            }

            const uploadButton = makeElement("button", "studio-action-link studio-action-add", "+ 上传新版");
            uploadButton.type = "button";
            uploadButton.dataset.studioAction = "upload";
            actions.appendChild(uploadButton);
            zone.appendChild(actions);
        } else {
            const hint = zone.querySelector(".drop-placeholder .text");
            if (hint) hint.textContent = FILE_HINTS[assetType];
            zone.setAttribute("role", "button");
            zone.setAttribute("tabindex", "0");
            zone.setAttribute("aria-label", FILE_HINTS[assetType]);
        }

        return zone.outerHTML;
    }

    /** Add a full-height inline script preview with an explicit dialog action. */
    function decorateShot(row, shot) {
        row.classList.add("studio-shot-card");
        const notesCell = row.querySelector(".notes-cell");
        if (!notesCell) return row;

        const head = makeElement("div", "studio-notes-head");
        head.appendChild(makeElement("span", "studio-notes-title", "分镜脚本"));
        const toggle = makeElement("button", "studio-notes-toggle", "展开全文");
        toggle.type = "button";
        toggle.dataset.studioAction = "notes";
        toggle.setAttribute("aria-haspopup", "dialog");
        toggle.setAttribute("aria-controls", "studio-notes-modal");
        head.appendChild(toggle);
        notesCell.insertBefore(head, notesCell.firstChild);

        const textarea = notesCell.querySelector(".notes-input");
        if (textarea) {
            textarea.setAttribute("aria-label", shot.name + " 分镜脚本");
            textarea.placeholder = "添加镜头说明、动作、英文对白…";
        }

        const shotName = row.querySelector(".shot-name");
        if (shotName) {
            shotName.setAttribute("title", "拖动以调整顺序 · 点击编辑镜头名称");
        }
        return row;
    }

    /** Update count pills after the existing uploader changes a media version. */
    function syncSlotCount(shotName, assetType, shot) {
        const row = document.getElementById("shot-row-" + shotName);
        const info = shot[assetType] || {};
        if (!row) return;
        const zone = row.querySelector('[data-studio-type="' + assetType + '"]');
        if (!zone) return;
        const count = zone.querySelector(".studio-version-count");
        if (count) count.textContent = "最高 v" + String(info.max_version || 0).padStart(3, "0");
        const badge = zone.querySelector(".version-badge");
        if (badge) badge.classList.toggle("multiple-versions", (info.max_version || 0) > 1);
        const currentButton = zone.querySelector(".studio-current-version");
        if (currentButton) {
            const currentVersion = info.current_version || info.max_version || 0;
            currentButton.textContent = "v" + String(currentVersion).padStart(3, "0") + " ▾";
        }
    }

    /** Build a small production summary from the currently loaded shot state. */
    function refreshStudioOverview() {
        const active = shots.filter(shot => !shot.archived);
        const ready = active.filter(shot => shot.video && shot.video.max_version > 0).length;
        const imageReady = active.filter(shot => shot.first_image && shot.first_image.max_version > 0).length;
        const total = active.length;
        const progress = total ? Math.round((ready / total) * 100) : 0;
        const values = {
            "studio-count-shots": String(total),
            "studio-count-images": String(imageReady),
            "studio-count-videos": String(ready),
            "studio-progress-label": progress + "%"
        };
        Object.entries(values).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        });
        const bar = document.getElementById("studio-progress-bar");
        if (bar) bar.style.width = progress + "%";
    }

    /** Show the actual shot identifiers returned after filesystem renumbering. */
    function refreshStudioOrderLabels() {
        if (window.StudioOrder) {
            window.StudioOrder.applyShotOrderLabels(shots, document);
        }
    }

    window.refreshStudioOrderLabels = refreshStudioOrderLabels;

    /** Reuse the working original renderer and uploads while improving presentation. */
    const originalDropZone = window.createDropZone;
    const originalShotRow = window.createShotRow;
    const originalRenderShots = window.renderShots;
    const originalUpdateDropZone = window.updateDropZoneForShot;
    const originalReplaceDropZone = window.replaceDropZoneForShot;

    if (typeof originalDropZone === "function") {
        window.createDropZone = function (shot, assetType) {
            return ASSET_TYPES.includes(assetType)
                ? decorateAsset(shot, assetType, originalDropZone(shot, assetType))
                : originalDropZone(shot, assetType);
        };
    }
    if (typeof originalShotRow === "function") {
        window.createShotRow = function (shot) {
            return decorateShot(originalShotRow(shot), shot);
        };
    }
    if (typeof originalRenderShots === "function") {
        window.renderShots = function (...args) {
            const result = originalRenderShots(...args);
            refreshStudioOrderLabels();
            refreshStudioOverview();
            return result;
        };
    }
    if (typeof originalUpdateDropZone === "function") {
        window.updateDropZoneForShot = function (shotName, assetType, shotData) {
            const result = originalUpdateDropZone(shotName, assetType, shotData);
            syncSlotCount(shotName, assetType, shotData);
            const target = document.getElementById("shot-row-" + shotName)
                ?.querySelector('[data-studio-type="' + assetType + '"]');
            applyFullResolutionPreview(shotName, assetType, shotData[assetType], target);
            refreshStudioOverview();
            return result;
        };
    }

    // First uploads use replaceDropZoneForShot rather than updateDropZoneForShot.
    // Keep production counters accurate for both upload paths.
    if (typeof originalReplaceDropZone === "function") {
        window.replaceDropZoneForShot = function (shotName, assetType, shotData) {
            const result = originalReplaceDropZone(shotName, assetType, shotData);
            refreshStudioOverview();
            return result;
        };
    }

    /** Pause and release all history videos/audio before hiding or replacing them. */
    function stopGalleryMedia() {
        const container = document.getElementById("studio-version-items");
        container.querySelectorAll("audio, video").forEach(media => {
            media.pause();
            media.removeAttribute("src");
            media.load();
        });
    }

    /** Display a clear, selectable card for each existing version of an asset. */
    function renderGalleryItems(data) {
        const container = document.getElementById("studio-version-items");
        const summary = document.getElementById("studio-version-subtitle");
        stopGalleryMedia();
        container.replaceChildren();

        const versions = data.versions || [];
        summary.textContent = "已保存 " + versions.length + " 个历史版本 · 选择一个作为当前素材";

        if (!versions.length) {
            container.appendChild(
                makeElement("p", "studio-gallery-empty", "尚无历史版本。上传素材后就可以在这里查看和比较。")
            );
            return;
        }

        versions.forEach(item => {
            const selected = item.version === data.current_version;
            const card = makeElement("article", "studio-version-card" + (selected ? " is-selected" : ""));

            const mediaBox = makeElement("div", "studio-version-media");
            let media;
            if (data.asset_type === "audio") {
                media = document.createElement("audio");
                media.controls = true;
                media.preload = "none";
            } else if (data.asset_type === "video" || data.asset_type === "alt_video") {
                media = document.createElement("video");
                media.controls = true;
                media.preload = "metadata";
                media.muted = true;
                media.playsInline = true;
            } else {
                media = document.createElement("img");
                media.loading = "lazy";
                media.alt = "版本 v" + String(item.version).padStart(3, "0");
            }
            media.src = item.url;
            mediaBox.appendChild(media);

            const label = makeElement("div", "studio-version-meta");
            const title = makeElement("strong", "", "v" + String(item.version).padStart(3, "0"));
            label.appendChild(title);
            if (selected) label.appendChild(makeElement("span", "studio-current-mark", "当前使用"));

            const actions = makeElement("div", "studio-version-actions");
            const choose = makeElement(
                "button",
                selected ? "studio-version-choose is-current" : "studio-version-choose",
                selected ? "✓ 已选用" : "设为当前版本"
            );
            choose.type = "button";
            choose.disabled = selected;
            choose.addEventListener("click", () => promoteVersion(item.version, choose));
            actions.appendChild(choose);

            if (data.asset_type === "first_image" || data.asset_type === "last_image") {
                const enlarge = makeElement("a", "studio-version-open", "查看原图 ↗");
                enlarge.href = item.url;
                enlarge.target = "_blank";
                enlarge.rel = "noopener noreferrer";
                actions.appendChild(enlarge);
            }

            card.append(mediaBox, label, actions);
            container.appendChild(card);
        });
    }

    /** Fetch the real version list; ignore responses from closed/replaced galleries. */
    async function reloadVersionGallery(session = gallery) {
        if (!session) return;
        const requestId = session.requestId = (session.requestId || 0) + 1;
        const url = "/api/shots/versions/" +
            encodeURIComponent(session.shot) + "/" + encodeURIComponent(session.assetType);
        const isLatestRequest = () => gallery === session && isCurrentProject(session) &&
            session.requestId === requestId;
        try {
            const response = await fetch(url, {cache: "no-store"});
            const result = await response.json();
            // Matching shot names alone do not identify a live gallery request.
            if (!isLatestRequest()) return;
            if (!response.ok || !result.success) {
                throw new Error(result.error || "读取历史版本失败");
            }
            session.data = result.data;
            renderGalleryItems(result.data);
        } catch (error) {
            // Superseded HTTP, transport and JSON failures are equally stale.
            if (isLatestRequest()) throw error;
        }
    }

    /** Promote a WIP version using a stable shot, type and project identity. */
    async function promoteVersion(version, button) {
        const session = gallery;
        if (!session || button.disabled) return;
        const {shot, assetType} = session;
        const promotionKey = session.projectPath + "/" + shot + "/" + assetType;
        if (pendingPromotions.has(promotionKey)) return;

        pendingPromotions.add(promotionKey);
        button.disabled = true;
        try {
            const response = await fetch("/api/shots/promote", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({shot_name: shot, asset_type: assetType, version})
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || "版本切换失败");
            }
            // Never apply data from the previous project to the new project's
            // shot list, even when both projects contain an SH001 folder.
            if (!isCurrentProject(session)) return;
            if (result.data && result.data.name && result.data.name !== shot) {
                throw new Error("返回的镜头与请求不一致");
            }

            const index = shots.findIndex(item => item.name === shot);
            if (index >= 0) shots[index] = result.data;
            if (typeof window.replaceDropZoneForShot === "function") {
                window.replaceDropZoneForShot(shot, assetType, result.data);
            }
            refreshStudioOverview();

            // A reopened gallery for this same asset must also reflect completion.
            // Reloading invalidates any older list request still in flight, while
            // unrelated shots, asset types and projects remain untouched.
            const active = gallery;
            if (active && active.projectPath === session.projectPath &&
                active.shot === shot && active.assetType === assetType) {
                await reloadVersionGallery(active);
                if (gallery === active && isCurrentProject(active)) {
                    showNotification("已使用 v" + String(version).padStart(3, "0"));
                }
            }
        } catch (error) {
            if (gallery === session && isCurrentProject(session)) {
                showNotification(error.message || "版本切换失败", "error");
            }
        } finally {
            pendingPromotions.delete(promotionKey);
            button.disabled = false;
        }
    }

    /** Open the version gallery from the visible management button or badge. */
    async function openVersionGallery(shot, assetType, trigger) {
        lastGalleryTrigger = trigger || document.activeElement;
        const session = {shot, assetType, projectPath: studioProjectPath(), data: null};
        gallery = session;
        const modal = document.getElementById("studio-version-modal");
        document.getElementById("studio-version-title").textContent =
            shot + " · " + LABELS[assetType] + "版本";
        document.getElementById("studio-version-subtitle").textContent = "正在读取历史版本…";
        stopGalleryMedia();
        document.getElementById("studio-version-items").replaceChildren();
        modal.hidden = false;
        document.body.classList.add("studio-dialog-open");
        document.getElementById("studio-version-close").focus();

        try {
            await reloadVersionGallery(session);
        } catch (error) {
            if (gallery !== session || !isCurrentProject(session)) return;
            const items = document.getElementById("studio-version-items");
            items.appendChild(makeElement("p", "studio-gallery-empty", error.message));
            showNotification(error.message || "读取历史版本失败", "error");
        }
    }

    /** Close dialog and return keyboard focus to the button that opened it. */
    function closeVersionGallery() {
        const modal = document.getElementById("studio-version-modal");
        stopGalleryMedia();
        modal.hidden = true;
        document.body.classList.remove("studio-dialog-open");
        gallery = null;
        if (lastGalleryTrigger && lastGalleryTrigger.isConnected) lastGalleryTrigger.focus();
        lastGalleryTrigger = null;
    }

    /** Upload a new version through the original uploader, then refresh the gallery. */
    function chooseVersionFile() {
        if (!gallery) return;
        const input = document.getElementById("studio-version-file");
        const type = gallery.assetType;
        input.value = "";
        input.accept = type === "audio" ? "audio/*" :
            type === "video" || type === "alt_video" ? "video/*" : "image/*";
        input.click();
    }

    // Script editing is intentionally separate from version management; a native
    // dialog keeps editing independent of card dimensions and enables Escape.
    const notesDialog = document.getElementById("studio-notes-modal");
    const notesEditor = document.getElementById("studio-notes-editor");
    const notesSaveButton = document.getElementById("studio-notes-save");
    let notesDialogState = null;
    let notesSaving = false;

    /** Open the complete script from the current inline value, including unsaved typing. */
    function openNotesDialog(row, trigger) {
        const preview = row.querySelector(".notes-input");
        if (!preview || !notesDialog || notesDialog.open) return;

        const shotName = row.id.replace(/^shot-row-/, "");
        const shot = shots.find(item => item.name === shotName);
        const title = (shot && shot.display_name) || shotName;
        notesDialogState = {shotName, trigger};

        document.getElementById("studio-notes-dialog-title").textContent =
            title + " · 分镜脚本";
        notesEditor.value = preview.value;
        notesDialog.showModal();
        notesEditor.focus();
    }

    /** Close without editing the inline script; saving is an explicit action. */
    function closeNotesDialog() {
        if (notesDialog.open && !notesSaving) notesDialog.close();
    }

    /** Persist edited script via ShotBase's existing notes API, then sync card state. */
    async function saveNotesDialog() {
        if (!notesDialogState || notesSaving) return;

        const {shotName} = notesDialogState;
        const value = notesEditor.value;
        notesSaving = true;
        notesSaveButton.disabled = true;
        notesSaveButton.textContent = "保存中…";

        try {
            const response = await fetch("/api/shots/notes", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({shot_name: shotName, notes: value})
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || "保存脚本失败");
            }

            const shot = shots.find(item => item.name === shotName);
            if (shot) shot.notes = value;
            const preview = document.getElementById("shot-row-" + shotName)
                ?.querySelector(".notes-input");
            if (preview) preview.value = value;
            notesDialog.close();
            showNotification("分镜脚本已保存");
        } catch (error) {
            showNotification(error.message || "保存脚本失败", "error");
        } finally {
            notesSaving = false;
            notesSaveButton.disabled = false;
            notesSaveButton.textContent = "保存脚本";
        }
    }

    // Keep native dialog close methods and focus restoration in one place.
    document.getElementById("studio-notes-close").addEventListener("click", closeNotesDialog);
    document.getElementById("studio-notes-cancel").addEventListener("click", closeNotesDialog);
    notesSaveButton.addEventListener("click", saveNotesDialog);
    notesDialog.addEventListener("cancel", event => {
        if (notesSaving) event.preventDefault();
    });
    notesDialog.addEventListener("close", () => {
        const trigger = notesDialogState && notesDialogState.trigger;
        notesDialogState = null;
        if (trigger && trigger.isConnected) trigger.focus();
    });
    notesDialog.addEventListener("click", event => {
        // Native dialog backdrop clicks target the dialog itself, not its panel.
        if (event.target !== notesDialog || notesSaving) return;
        const bounds = notesDialog.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right ||
            event.clientY < bounds.top || event.clientY > bounds.bottom) {
            closeNotesDialog();
        }
    });

    /** Reveal the existing caption field only while the user edits the note.
     *
     * The original caption field retains its onblur/onchange save handler.
     * This avoids a second backend write path and does not alter media files.
     */
    function toggleCaptionEditor(zone, trigger) {
        const caption = zone?.querySelector(".asset-caption-input");
        if (!caption) return;

        const isOpen = zone.classList.toggle("studio-caption-visible");
        trigger.setAttribute("aria-expanded", String(isOpen));
        if (isOpen) caption.focus();
    }

    document.addEventListener("click", event => {
        const badge = event.target.closest(".studio-asset .version-badge");
        const action = event.target.closest("[data-studio-action]");
        if (badge || action) {
            const zone = event.target.closest(".studio-asset");
            if (zone && (badge || action.dataset.studioAction !== "notes")) {
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                if (badge || action.dataset.studioAction === "versions") {
                    openVersionGallery(zone.dataset.studioShot, zone.dataset.studioType, badge || action);
                } else if (action.dataset.studioAction === "upload") {
                    openFileDialog(zone.dataset.studioShot, zone.dataset.studioType);
                } else if (action.dataset.studioAction === "prompt") {
                    // The existing prompt modal reads its version from this
                    // original button, including after an upload or promotion.
                    const promptButton = zone.querySelector(".prompt-button");
                    if (promptButton) promptButton.click();
                } else if (action.dataset.studioAction === "caption") {
                    toggleCaptionEditor(zone, action);
                }
                return;
            }
            if (action && action.dataset.studioAction === "notes") {
                event.preventDefault();
                const row = action.closest(".studio-shot-card");
                if (row) openNotesDialog(row, action);
            }
        }
        if (event.target.id === "studio-version-close" ||
            event.target.classList.contains("studio-version-backdrop")) {
            closeVersionGallery();
        }
        if (event.target.id === "studio-version-upload") chooseVersionFile();
        if (event.target.id === "studio-density-toggle") {
            const main = document.getElementById("main-interface");
            const compact = main.classList.toggle("studio-compact");
            event.target.textContent = compact ? "切换宽松视图" : "切换紧凑视图";
            event.target.setAttribute("aria-pressed", String(compact));
        }
    }, true);

    document.addEventListener("keydown", event => {
        // Keep keyboard focus inside the version picker while it is open.
        if (event.key === "Tab" && gallery) {
            const panel = document.querySelector("#studio-version-modal .studio-version-panel");
            const controls = [...panel.querySelectorAll(
                'button:not([disabled]), a[href], input:not([disabled]):not([hidden])'
            )].filter(node => node.getClientRects().length > 0);
            if (controls.length) {
                const first = controls[0];
                const last = controls[controls.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                    event.preventDefault();
                    last.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                    event.preventDefault();
                    first.focus();
                }
            }
        }
        if (event.key === "Escape" && gallery) {
            event.preventDefault();
            closeVersionGallery();
        }
        if ((event.key === "Enter" || event.key === " ") &&
            event.target.matches(".studio-asset.empty, .studio-asset .version-badge")) {
            event.preventDefault();
            event.target.click();
        }
    });

    document.getElementById("studio-version-file").addEventListener("change", async event => {
        const file = event.target.files && event.target.files[0];
        if (!file || !gallery) return;
        const session = gallery;
        const shot = session.shot;
        const assetType = session.assetType;
        const uploadButton = document.getElementById("studio-version-upload");
        uploadButton.disabled = true;
        uploadButton.textContent = "正在上传…";
        try {
            await uploadFile(file, shot, assetType);
            if (gallery === session && isCurrentProject(session)) {
                await reloadVersionGallery(session);
            }
        } catch (error) {
            showNotification(error.message || "上传失败", "error");
        } finally {
            uploadButton.disabled = false;
            uploadButton.textContent = "+ 上传新版本";
        }
    });

    document.body.classList.add("studio-design");

    const densityButton = document.getElementById("studio-density-toggle");
    if (densityButton) {
        document.getElementById("main-interface").classList.add("studio-compact");
        densityButton.textContent = "切换宽松视图";
        densityButton.setAttribute("aria-pressed", "true");
    }
})();
