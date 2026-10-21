/* Shot labels for the storyboard UI.
 *
 * Show the actual media identifier. Reordering renumbers directories and assets
 * on the server and replaces the client shot data with the updated identifiers.
 */
(function attachStudioOrder(root, createModule) {
    const api = createModule();
    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
    if (root) root.StudioOrder = api;
})(typeof window !== "undefined" ? window : null, function createStudioOrder() {
    "use strict";

    const numericDisplayName = /^SH\d{3}(?:_\d{3})?$/i;

    /** Match headings to the shot names used for media paths and uploads. */
    function computeVisibleShotLabels(shots) {
        return shots.map(shot => {
            const archived = !!shot.archived;
            const number = shot.name;
            const displayName = typeof shot.display_name === "string"
                ? shot.display_name
                : "";
            const trimmed = displayName.trim();

            return {
                shotId: shot.name,
                number,
                archived,
                displayName,
                // Old user-entered SH003 / SH004 values described positions, not
                // scenes; do not render those stale numbers as subtitles.
                subtitle: numericDisplayName.test(trimmed) ? "" : trimmed
            };
        });
    }

    /** Update a label without discarding its click event or DOM attributes. */
    function renderLabel(container, label, doc, isSidebar) {
        if (!container) return;

        const title = doc.createElement("span");
        title.className = isSidebar ? "shot-display-name" : "studio-order-number";
        title.textContent = label.number;

        const pieces = [title];
        if (label.subtitle) {
            const description = doc.createElement("span");
            description.className = isSidebar ? "shot-code" : "studio-order-subtitle";
            description.textContent = label.subtitle;
            pieces.push(description);
        }

        container.replaceChildren(...pieces);
        container.title = label.archived
            ? "已归档；内部素材 ID：" + label.shotId
            : "拖动排序 · " + label.number + "；内部素材 ID：" + label.shotId;
        if (!isSidebar) container.dataset.displayName = label.displayName;
    }

    /** Refresh card and TOC labels from the latest server-provided shot names. */
    function applyShotOrderLabels(shots, doc) {
        if (!doc || !Array.isArray(shots)) return [];

        const labels = computeVisibleShotLabels(shots);
        const tocItems = new Map(
            Array.from(doc.querySelectorAll(".toc-item")).map(node => [
                node.dataset.target,
                node
            ])
        );

        labels.forEach(label => {
            const rowId = "shot-row-" + label.shotId;
            const row = doc.getElementById(rowId);
            const title = row ? row.querySelector(".shot-name") : null;
            renderLabel(title, label, doc, false);
            renderLabel(tocItems.get(rowId), label, doc, true);
        });
        return labels;
    }

    return {computeVisibleShotLabels, applyShotOrderLabels};
});
