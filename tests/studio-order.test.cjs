/* Regression tests for stable shot identities and position-based UI numbering. */
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");

/**
 * Load shot numbering as a Node module. The browser uses the same implementation
 * through window.StudioOrder, without any build-time dependencies.
 */
function loadOrder() {
    return require(path.join(__dirname, "..", "app", "static", "js", "studio-order.js"));
}

/** Provide a tiny DOM-like surface to validate rendered titles and TOC labels. */
function fakeDocument(shotNames) {
    const rows = new Map();
    const items = new Map();
    for (const shotName of shotNames) {
        const title = {
            dataset: {},
            title: "",
            children: [],
            replaceChildren(...children) {
                this.children = children;
            }
        };
        rows.set(shotName, {querySelector: () => title, title});
        const toc = {
            dataset: {target: "shot-row-" + shotName},
            title: "",
            children: [],
            replaceChildren(...children) {
                this.children = children;
            }
        };
        items.set(shotName, toc);
    }

    const document = {
        createElement(tag) {
            return {tagName: tag, className: "", textContent: ""};
        },
        getElementById(id) {
            return rows.get(id.replace(/^shot-row-/, "")) || null;
        },
        querySelectorAll(selector) {
            if (selector === ".toc-item") return Array.from(items.values());
            return [];
        }
    };
    return {document, rows, items};
}

test("swapping two shots automatically renumbers visible headings without renaming their IDs", () => {
    const StudioOrder = loadOrder();
    const shots = [
        {name: "SH001"},
        {name: "SH002"},
        {name: "SH004", display_name: "SH003"},
        {name: "SH003", display_name: "SH004"}
    ];
    const before = JSON.parse(JSON.stringify(shots));
    const labels = StudioOrder.computeVisibleShotLabels(shots);
    assert.deepEqual(labels.map(x => x.number), ["SH001", "SH002", "SH003", "SH004"]);
    assert.deepEqual(labels.map(x => x.shotId), ["SH001", "SH002", "SH004", "SH003"]);
    assert.equal(labels[2].subtitle, "");
    assert.equal(labels[3].subtitle, "");
    assert.deepEqual(shots, before);
});

test("descriptive names remain visible while numeric display names are ignored", () => {
    const StudioOrder = loadOrder();
    const result = StudioOrder.computeVisibleShotLabels([
        {name: "SH004", display_name: "下床啦"},
        {name: "SH003", display_name: "SH004"},
        {name: "SH005", display_name: "  SH003  "},
        {name: "SH006_050", display_name: "Wake Up!"}
    ]);
    assert.equal(result[0].number, "SH001");
    assert.equal(result[0].subtitle, "下床啦");
    assert.equal(result[1].number, "SH002");
    assert.equal(result[1].subtitle, "");
    assert.equal(result[2].subtitle, "");
    assert.equal(result[3].subtitle, "Wake Up!");
});

test("archived shots are skipped when assigning active sequence numbers", () => {
    const StudioOrder = loadOrder();
    const result = StudioOrder.computeVisibleShotLabels([
        {name: "SH002", archived: false},
        {name: "SH004", archived: true, display_name: "Archived"},
        {name: "SH003", archived: false}
    ]);
    assert.deepEqual(result.map(x => x.number), ["SH001", "SH004", "SH002"]);
    assert.equal(result[1].archived, true);
    assert.equal(result[1].subtitle, "Archived");
});

test("reorder updates cards and sidebar labels while preserving stable DOM IDs", () => {
    const StudioOrder = loadOrder();
    const shots = [
        {name: "SH001", display_name: "Wake Up!"},
        {name: "SH004", display_name: "SH003"},
        {name: "SH003", display_name: "下床啦"}
    ];
    const ui = fakeDocument(shots.map(x => x.name));

    StudioOrder.applyShotOrderLabels(shots, ui.document);
    assert.deepEqual(
        ui.rows.get("SH004").title.children.map(x => x.textContent), ["SH002"]
    );
    assert.deepEqual(
        ui.items.get("SH003").children.map(x => x.textContent), ["SH003", "下床啦"]
    );
    assert.equal(ui.rows.get("SH004").title.dataset.displayName, "SH003");
    assert.match(ui.rows.get("SH004").title.title, /内部素材 ID：SH004/);

    const order = ["SH001", "SH003", "SH004"];
    shots.sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name));
    StudioOrder.applyShotOrderLabels(shots, ui.document);

    assert.equal(ui.rows.get("SH003").title.children[0].textContent, "SH002");
    assert.equal(ui.items.get("SH003").children[0].textContent, "SH002");
    assert.equal(ui.rows.get("SH004").title.children[0].textContent, "SH003");
    assert.equal(ui.items.get("SH004").children[0].textContent, "SH003");
    assert.equal(ui.rows.get("SH004").title.dataset.displayName, "SH003");
    assert.equal(ui.rows.size, 3);
});


test("the page and all reorder/edit paths refresh the position-derived labels", () => {
    const root = path.join(__dirname, "..");
    const html = fs.readFileSync(path.join(root, "app/templates/index.html"), "utf8");
    const main = fs.readFileSync(path.join(root, "app/static/js/main.js"), "utf8");
    const studio = fs.readFileSync(path.join(root, "app/static/js/studio.js"), "utf8");
    assert.ok(
        html.indexOf("js/studio-order.js") >= 0 &&
        html.indexOf("js/studio-order.js") < html.indexOf("js/studio.js"),
        "the numbering module must load before studio.js"
    );
    assert.match(studio, /StudioOrder\.applyShotOrderLabels\(shots, document\)/);
    assert.match(main, /renderTOC\(\);\s*window\.refreshStudioOrderLabels\?\.\(\)/);
    assert.match(main, /saveDisplayName\([\s\S]*?renderTOC\(\);\s*window\.refreshStudioOrderLabels\?\.\(\)/);
});
