const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../app/static/js/main.js"), "utf8");
const handler = source.slice(source.indexOf("async function archiveShot("), source.indexOf("async function revealFile("));

for (const archived of [true, false]) {
    test(`${archived ? "archive" : "unarchive"} renders the updated list and scrolls to the moved shot`, async () => {
        const updated = {name: "SH001", archived};
        const saved = new Map();
        const messages = [];
        let rendered = false;
        let scrolled = false;
        const context = {
            shots: [{name: "SH001", archived: !archived}],
            fetch: async () => ({json: async () => ({success: true, data: updated})}),
            localStorage: {setItem: (key, value) => saved.set(key, value)},
            captureScroll: () => {},
            renderShots: () => {
                assert.equal(context.shots[0], updated);
                if (archived) assert.equal(saved.get("archivedOpen"), "true");
                rendered = true;
            },
            requestAnimationFrame: callback => callback(),
            document: {getElementById: id => {
                assert.equal(id, "shot-row-SH001");
                return {querySelector: () => null, scrollIntoView: () => {
                    assert.equal(rendered, true);
                    scrolled = true;
                }};
            }},
            showNotification: message => messages.push(message),
            console
        };
        vm.runInNewContext(handler, context);
        await context.archiveShot("SH001", archived);
        assert.equal(rendered, true);
        assert.equal(scrolled, true);
        assert.equal(messages.some(message => message.includes("Refresh")), false);
    });
}
