// Interaction tests for compact first-frame tools without a DOM dependency.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.join(__dirname, "..", "app", "static", "js", "studio.js"),
    "utf8"
);

/**
 * Run the production delegated-click handler with a minimal fake ShotBase UI.
 * Only native methods touched by the compact action handling are provided.
 */
function createHarness() {
    const events = {};
    const visibleClasses = new Set();
    const caption = {
        focused: false,
        focus() {
            this.focused = true;
        }
    };
    const prompt = {
        clicked: 0,
        click() {
            this.clicked += 1;
        }
    };
    const zone = {
        dataset: {studioShot: "SH001", studioType: "first_image"},
        classList: {
            toggle(name) {
                if (visibleClasses.has(name)) {
                    visibleClasses.delete(name);
                    return false;
                }
                visibleClasses.add(name);
                return true;
            },
            contains(name) {
                return visibleClasses.has(name);
            }
        },
        querySelector(selector) {
            if (selector === ".asset-caption-input") return caption;
            if (selector === ".prompt-button") return prompt;
            return null;
        }
    };
    const noop = () => {};
    const dummy = {addEventListener: noop, focus: noop, open: false};
    const controls = new Map([
        ["studio-notes-modal", {...dummy}],
        ["studio-notes-editor", {...dummy}],
        ["studio-notes-save", {...dummy}],
        ["studio-notes-close", {...dummy}],
        ["studio-notes-cancel", {...dummy}],
        ["studio-version-file", {...dummy}],
        ["studio-density-toggle", {...dummy}]
    ]);
    const context = {
        shots: [],
        window: {},
        document: {
            getElementById(id) {
                return controls.get(id) || null;
            },
            addEventListener(type, fn) {
                (events[type] ||= []).push(fn);
            },
            body: {classList: {add: noop}}
        },
        localStorage: {getItem: () => null, setItem: noop},
        showNotification: noop,
        console
    };

    vm.runInNewContext(source, context, {filename: "studio.js"});

    /** Dispatch the same event shape that a footer button produces. */
    function clickAction(type) {
        const attributes = {};
        const target = {
            dataset: {studioAction: type},
            id: "",
            classList: {contains: () => false},
            setAttribute(name, value) {
                attributes[name] = value;
            },
            closest(selector) {
                if (selector === "[data-studio-action]") return this;
                if (selector === ".studio-asset") return zone;
                return null;
            }
        };
        for (const fn of events.click || []) {
            fn({target, preventDefault: noop, stopPropagation: noop, stopImmediatePropagation: noop});
        }
        return attributes;
    }

    return {clickAction, caption, prompt, visibleClasses};
}

test("first-frame caption opens only on request and can be closed again", () => {
    const ui = createHarness();
    assert.equal(ui.visibleClasses.has("studio-caption-visible"), false);

    const openAttributes = ui.clickAction("caption");
    assert.equal(ui.visibleClasses.has("studio-caption-visible"), true);
    assert.equal(openAttributes["aria-expanded"], "true");
    assert.equal(ui.caption.focused, true);

    const closeAttributes = ui.clickAction("caption");
    assert.equal(ui.visibleClasses.has("studio-caption-visible"), false);
    assert.equal(closeAttributes["aria-expanded"], "false");
});

test("compact prompt action reuses the original ShotBase prompt control", () => {
    const ui = createHarness();
    ui.clickAction("prompt");
    assert.equal(ui.prompt.clicked, 1);
    assert.equal(ui.visibleClasses.has("studio-caption-visible"), false);
});
