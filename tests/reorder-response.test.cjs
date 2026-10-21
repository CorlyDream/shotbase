/* All reorder controls must replace stale asset IDs and paths after renaming. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(file, start, end) {
    const text = fs.readFileSync(path.join(__dirname, "..", "app/static/js", file), "utf8");
    return text.slice(text.indexOf(start), text.indexOf(end, text.indexOf(start)));
}

for (const mode of ["drag", "list", "visual"]) {
    test(`${mode} reorder renders the returned shot IDs, paths and versions`, async () => {
        const oldShots = [{name: "SH001"}, {name: "SH002"}];
        const updated = [
            {name: "SH001", display_name: "Second scene", first_image: {file: "/latest_images/SH001_first.png", current_version: 2}},
            {name: "SH002", display_name: "First scene", first_image: {file: "/latest_images/SH002_first.png", current_version: 1}}
        ];
        const children = ["SH002", "SH001"].map(name => ({
            id: `shot-row-${name}`, classList: {contains: () => true},
            dataset: {name, shotName: name}
        }));
        let onEnd;
        let rendered;
        let requested;
        const context = {
            shots: oldShots,
            shotOrderRevision: "before",
            shotReorderPending: false,
            document: {
                getElementById: () => ({children, querySelectorAll: () => children}),
                querySelectorAll: () => children
            },
            Sortable: function (_element, options) { onEnd = options.onEnd; },
            fetch: async (_url, options) => {
                requested = JSON.parse(options.body);
                return {json: async () => ({success: true, data: {shots: updated, order_revision: "after"}})};
            },
            renderShots: () => { rendered = context.shots; },
            renderTOC: () => {}, showNotification: () => {},
            loadShots: () => { throw new Error("Unexpected reload"); },
            closeReorderModal: () => {}, closeVisualReorderModal: () => {},
            window: {}, console
        };
        vm.runInNewContext(source("main.js", "async function persistShotOrder(", "function initSortable()"), context);
        if (mode === "drag") {
            vm.runInNewContext(source("main.js", "function initSortable()", "// Helper to safely escape HTML"), context);
            context.initSortable();
            await onEnd({});
        } else if (mode === "list") {
            vm.runInNewContext(source("main.js", "async function saveReorder()", "// Filter functionality for reorder modal"), context);
            await context.saveReorder();
        } else {
            vm.runInNewContext(source("visual-reorder.js", "async function saveVisualReorder()", "// Preview/Playback"), context);
            await context.saveVisualReorder();
        }
        assert.deepEqual(requested.shot_order, ["SH002", "SH001"]);
        assert.equal(context.shots, updated);
        assert.equal(rendered, updated);
        assert.equal(requested.revision, "before");
        assert.equal(context.shotOrderRevision, "after");
        assert.equal(context.shotReorderPending, false);
    });
}

test("pending saves are sent once and a stale response reloads authoritative shot data", async () => {
    let finish;
    let requests = 0;
    let reloads = 0;
    const context = {
        shots: [{name: "SH001"}, {name: "SH002"}],
        shotOrderRevision: "old", shotReorderPending: false,
        fetch: () => {
            requests += 1;
            return new Promise(resolve => { finish = resolve; });
        },
        loadShots: async () => {
            reloads += 1;
            context.shots = [{name: "SH001", display_name: "Fresh scene"}];
            context.shotOrderRevision = "fresh";
        },
        renderShots: () => { throw new Error("A rejected save must reload first"); },
        showNotification: () => {}, console
    };
    vm.runInNewContext(source("main.js", "async function persistShotOrder(", "function initSortable()"), context);
    const pending = context.persistShotOrder(["SH002", "SH001"]);
    assert.equal(await context.persistShotOrder(["SH002", "SH001"]), false);
    assert.equal(requests, 1);
    finish({json: async () => ({success: false, error: "Shot order changed"})});
    assert.equal(await pending, false);
    assert.equal(reloads, 1);
    assert.equal(context.shotOrderRevision, "fresh");
    assert.equal(context.shotReorderPending, false);
});
