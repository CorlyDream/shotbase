/* Real studio.js handlers exercised with a lightweight DOM and deferred HTTP calls. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.join(__dirname, "..", "app", "static", "js", "studio.js"), "utf8"
);

/** An event-capable DOM substitute that records media cleanup operations. */
function makeNode(tag = "div") {
    const listeners = new Map();
    const classes = new Set();
    return {
        tagName: tag.toUpperCase(),
        className: "",
        dataset: {},
        style: {},
        children: [],
        id: "",
        textContent: "",
        hidden: false,
        disabled: false,
        src: "",
        currentTime: 12,
        pauseCount: 0,
        loadCount: 0,
        isConnected: true,
        classList: {
            add: (...names) => names.forEach(name => classes.add(name)),
            remove: (...names) => names.forEach(name => classes.delete(name)),
            contains: name => classes.has(name),
            toggle(name) {
                if (classes.has(name)) { classes.delete(name); return false; }
                classes.add(name);
                return true;
            }
        },
        addEventListener(type, callback) {
            if (!listeners.has(type)) listeners.set(type, []);
            listeners.get(type).push(callback);
        },
        fire(type, event = {}) {
            return Promise.all((listeners.get(type) || []).map(listener => listener(event)));
        },
        append(...nodes) { this.children.push(...nodes); },
        appendChild(node) { this.children.push(node); },
        replaceChildren(...nodes) { this.children = nodes; },
        querySelectorAll(selector) {
            if (selector !== "audio, video") return [];
            const results = [];
            const collect = node => {
                if (["AUDIO", "VIDEO"].includes(node.tagName)) results.push(node);
                for (const child of node.children || []) collect(child);
            };
            collect(this);
            return results;
        },
        querySelector() { return null; },
        closest() { return null; },
        focus() { this.focused = true; },
        getClientRects() { return [{}]; },
        setAttribute(key, value) { this[key] = value; },
        removeAttribute(key) { if (key === "src") this.src = ""; },
        pause() { this.pauseCount++; },
        load() { this.loadCount++; }
    };
}

/** Initialize the actual production script with shots and a real async queue. */
function harness() {
    const listeners = new Map();
    const nodes = new Map();
    const container = makeNode();
    const modal = makeNode();
    modal.hidden = true;
    const notifications = [];
    const promotions = [];
    const replaced = [];
    const shots = [
        {name: "SH001", video: {max_version: 2, current_version: 1}, first_image: {max_version: 0}},
        {name: "SH002", video: {max_version: 2, current_version: 1}, first_image: {max_version: 0}}
    ];
    const layouts = new Map();
    const lists = new Map([
        ["SH001", [1, 2]],
        ["SH002", [1, 2]]
    ]);
    for (const id of [
        "studio-version-title", "studio-version-subtitle", "studio-version-close",
        "studio-version-upload", "studio-version-file", "studio-notes-modal",
        "studio-notes-editor", "studio-notes-save", "studio-notes-close",
        "studio-notes-cancel", "studio-density-toggle", "main-interface",
        "studio-count-shots", "studio-count-images", "studio-count-videos",
        "studio-progress-bar", "studio-progress-label"
    ]) {
        nodes.set(id, makeNode());
    }
    nodes.set("studio-version-items", container);
    nodes.set("studio-version-modal", modal);

    const doc = {
        createElement: makeNode,
        getElementById: id => nodes.get(id) || null,
        querySelectorAll(selector) {
            if (selector === ".toc-item") return [];
            if (selector.includes("studio-version-items") &&
                (selector.includes("audio") || selector.includes("video"))) {
                return container.querySelectorAll("audio, video");
            }
            return [];
        },
        addEventListener(type, callback) {
            if (!listeners.has(type)) listeners.set(type, []);
            listeners.get(type).push(callback);
        },
        body: {classList: makeNode().classList},
        activeElement: null
    };

    function fetch(url, options) {
        if (url.startsWith("/api/shots/versions/")) {
            const shot = url.split("/")[4];
            const items = lists.get(shot) || [1];
            return Promise.resolve({
                ok: true,
                json: async () => ({
                    success: true,
                    data: {
                        shot_name: shot,
                        asset_type: "video",
                        current_version: 1,
                        versions: items.map(version => ({
                            version,
                            url: "/media/" + shot + "/" + version
                        }))
                    }
                })
            });
        }
        if (url === "/api/shots/promote") {
            return new Promise(resolve => promotions.push({
                resolve,
                payload: JSON.parse(options.body)
            }));
        }
        throw new Error("Unexpected HTTP call: " + url);
    }

    const ctx = {
        document: doc,
        window: {
            replaceDropZoneForShot: (shot, type, data) => replaced.push({shot, type, data}),
            updateDropZoneForShot: () => undefined
        },
        localStorage: {getItem: () => "true", setItem() {}},
        currentProject: {path: "/project-a"},
        shots,
        fetch,
        showNotification: (message, type) => notifications.push({message, type}),
        console
    };
    vm.runInNewContext(source, ctx, {filename: "studio.js"});

    /** Send a delegated UI action, following the existing event listener. */
    function click(action, shot = "SH001", assetType = "video") {
        const zone = {dataset: {studioShot: shot, studioType: assetType}};
        const target = {
            id: "",
            dataset: {studioAction: action},
            classList: {contains: () => false},
            closest(selector) {
                if (selector === ".studio-asset .version-badge") return null;
                if (selector === "[data-studio-action]") return this;
                if (selector === ".studio-asset") return zone;
                return null;
            }
        };
        const event = {
            target,
            preventDefault() {},
            stopPropagation() {},
            stopImmediatePropagation() {}
        };
        for (const callback of listeners.get("click") || []) callback(event);
    }
    function close() {
        const event = {
            target: {
                id: "studio-version-close",
                classList: {contains: () => false},
                closest: () => null
            }
        };
        for (const callback of listeners.get("click") || []) callback(event);
    }
    function chooseSecond() {
        const card = container.children.find(node =>
            node.children[1]?.children[0]?.textContent === "v002");
        assert.ok(card, "v002 card should have been rendered");
        return card.children[2].children[0].fire("click");
    }
    function finishPromotion(index = 0) {
        const pending = promotions[index];
        assert.ok(pending, "expected an in-flight promotion");
        pending.resolve({
            ok: true,
            json: async () => ({
                success: true,
                data: {name: pending.payload.shot_name, video: {
                    current_version: pending.payload.version, max_version: 2
                }}
            })
        });
    }
    const tick = () => new Promise(resolve => setImmediate(resolve));

    return {
        ctx, nodes, doc, container, modal, promotions, replaced, shots, notifications,
        lists, click, close, chooseSecond, finishPromotion, tick
    };
}

test("closing the gallery while promotion is pending still updates the correct shot", async () => {
    const h = harness();
    h.click("versions", "SH001");
    await h.tick();
    const pending = h.chooseSecond();
    await h.tick();
    h.close();
    h.finishPromotion();
    await pending;

    assert.equal(h.shots[0].video.current_version, 2);
    assert.equal(h.shots[1].video.current_version, 1);
    assert.equal(h.replaced[0].shot, "SH001");
    assert.equal(h.modal.hidden, true);
    assert.equal(h.notifications.some(x => x.type === "error"), false);
});

test("old promotion cannot overwrite a newer gallery's shot or selected version", async () => {
    const h = harness();
    h.click("versions", "SH001");
    await h.tick();
    const pending = h.chooseSecond();
    await h.tick();
    h.click("versions", "SH002");
    await h.tick();
    const title = h.nodes.get("studio-version-title").textContent;
    h.finishPromotion();
    await pending;

    assert.equal(h.shots[0].video.current_version, 2);
    assert.equal(h.shots[1].video.current_version, 1);
    assert.equal(h.replaced[0].shot, "SH001");
    assert.equal(h.nodes.get("studio-version-title").textContent, title);
    assert.equal(h.container.children[0].children[1].children[1].textContent, "当前使用");
});

test("a response from the previous project cannot overwrite newly opened project state", async () => {
    const h = harness();
    h.click("versions", "SH001");
    await h.tick();
    const pending = h.chooseSecond();
    await h.tick();
    h.ctx.currentProject = {path: "/project-b"};
    h.shots[0] = {name: "SH001", video: {current_version: 1, max_version: 2}};
    h.finishPromotion();
    await pending;
    assert.equal(h.shots[0].video.current_version, 1);
    assert.equal(h.replaced.length, 0);
});

test("closing the gallery stops and releases hidden video and audio playback", async () => {
    const h = harness();
    h.click("versions", "SH001");
    await h.tick();
    const playing = h.container.querySelectorAll("audio, video");
    assert.equal(playing.length, 2);
    playing.forEach(media => { media.currentTime = 8; });

    h.close();
    assert.equal(h.modal.hidden, true);
    for (const media of playing) {
        assert.equal(media.pauseCount, 1);
        assert.equal(media.src, "");
        assert.ok(media.loadCount >= 1);
    }
});

test("uploading the first image or video updates overview without a full rerender", () => {
    const h = harness();
    h.shots[0].first_image.max_version = 1;
    h.ctx.window.replaceDropZoneForShot("SH001", "first_image", h.shots[0]);
    assert.equal(h.nodes.get("studio-count-images").textContent, "1");

    h.shots[0].video.max_version = 1;
    h.shots[1].video.max_version = 0;
    h.ctx.window.replaceDropZoneForShot("SH001", "video", h.shots[0]);
    assert.equal(h.nodes.get("studio-count-videos").textContent, "1");
    assert.equal(h.nodes.get("studio-progress-label").textContent, "50%");
});
