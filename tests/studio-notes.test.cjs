// No browser-test dependencies: exercises the real studio.js dialog handlers.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const studioScript = fs.readFileSync(
    path.join(__dirname, "..", "app", "static", "js", "studio.js"), "utf8"
);

/** Create an event-capable element using only the Node.js test runner. */
function element(extra = {}) {
    const listeners = new Map();
    return {
        ...extra,
        addEventListener(type, callback) {
            const list = listeners.get(type) || [];
            list.push(callback);
            listeners.set(type, list);
        },
        async emit(type, event = {}) {
            for (const callback of listeners.get(type) || []) await callback(event);
        },
        focus() {
            this.wasFocused = true;
        }
    };
}

/** Execute the production script with just the DOM APIs used by the notes flow. */
function makeStudioHarness() {
    const documentListeners = {};
    const messages = [];
    const requests = [];
    const preview = {value: "小熊伸懒腰。"};
    const row = {
        id: "shot-row-SH001",
        querySelector(selector) {
            return selector === ".notes-input" ? preview : null;
        }
    };
    const action = element({
        dataset: {studioAction: "notes"},
        classList: {contains() { return false; }},
        isConnected: true,
        closest(selector) {
            if (selector === "[data-studio-action]") return this;
            if (selector === ".studio-shot-card") return row;
            return null;
        }
    });

    const dialog = element({
        open: false,
        showModal() {
            this.open = true;
        },
        close() {
            this.open = false;
            void this.emit("close");
        },
        getBoundingClientRect() {
            return {left: 100, right: 500, top: 100, bottom: 500};
        }
    });
    const editor = element({value: ""});
    const saveButton = element({textContent: "保存脚本", disabled: false});
    const title = element({textContent: ""});
    const nodes = {
        "studio-notes-modal": dialog,
        "studio-notes-editor": editor,
        "studio-notes-save": saveButton,
        "studio-notes-close": element(),
        "studio-notes-cancel": element(),
        "studio-notes-dialog-title": title,
        "studio-version-file": element(),
        "studio-version-items": element(),
        "studio-density-toggle": element(),
        "shot-row-SH001": row
    };
    const shots = [{name: "SH001", display_name: "Wake Up!", notes: preview.value}];
    let httpResult = {ok: true, body: {success: true}};

    const sandbox = {
        document: {
            getElementById(id) {
                return nodes[id] || null;
            },
            addEventListener(type, callback) {
                (documentListeners[type] ||= []).push(callback);
            },
            body: {classList: {add() {}}},
            createElement() {
                throw new Error("Not expected while testing notes dialogs");
            }
        },
        window: {},
        shots,
        localStorage: {getItem() { return null; }, setItem() {}},
        fetch: async (url, options) => {
            requests.push({url, options});
            return {ok: httpResult.ok, json: async () => httpResult.body};
        },
        showNotification: (message, kind) => messages.push({message, kind}),
        console
    };

    vm.runInNewContext(studioScript, sandbox, {filename: "studio.js"});

    /** Mimic a real click on the per-shot “展开全文” button. */
    function open() {
        const clickEvent = {target: action, preventDefault() {}};
        for (const listener of documentListeners.click || []) listener(clickEvent);
    }

    return {
        preview,
        editor,
        dialog,
        title,
        shots,
        requests,
        messages,
        action,
        open,
        save: () => saveButton.emit("click"),
        cancel: () => nodes["studio-notes-cancel"].emit("click"),
        failSave() {
            httpResult = {ok: false, body: {success: false, error: "保存失败"}};
        }
    };
}

test("expand opens a full-text native dialog without changing card content", async () => {
    const ui = makeStudioHarness();
    ui.open();
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.editor.value, "小熊伸懒腰。");
    assert.equal(ui.title.textContent, "Wake Up! · 分镜脚本");
    assert.equal(ui.editor.wasFocused, true);
    assert.equal(ui.preview.value, "小熊伸懒腰。");
});

test("saving the modal posts notes and refreshes the existing card", async () => {
    const ui = makeStudioHarness();
    ui.open();
    ui.editor.value = "完整分镜：\n小熊起床。";
    await ui.save();
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.requests[0].url, "/api/shots/notes");
    assert.deepEqual(
        JSON.parse(ui.requests[0].options.body),
        {shot_name: "SH001", notes: "完整分镜：\n小熊起床。"}
    );
    assert.equal(ui.shots[0].notes, "完整分镜：\n小熊起床。");
    assert.equal(ui.preview.value, "完整分镜：\n小熊起床。");
    assert.equal(ui.dialog.open, false);
});

test("cancel discards modal-only changes without touching saved notes", async () => {
    const ui = makeStudioHarness();
    ui.open();
    ui.editor.value = "本次修改不要保存";
    await ui.cancel();
    assert.equal(ui.dialog.open, false);
    assert.equal(ui.preview.value, "小熊伸懒腰。");
    assert.equal(ui.requests.length, 0);
});

test("failed save keeps editor open and does not overwrite card state", async () => {
    const ui = makeStudioHarness();
    ui.failSave();
    ui.open();
    ui.editor.value = "尝试保存";
    await ui.save();
    assert.equal(ui.dialog.open, true);
    assert.equal(ui.preview.value, "小熊伸懒腰。");
    assert.equal(ui.shots[0].notes, "小熊伸懒腰。");
    assert.equal(ui.messages[0].kind, "error");
});
