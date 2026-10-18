/* The Python bridge prefixes this file with a bounded, validated v1 manifest. */
(function () {
  "use strict";
  const manifest = oldRussiaExportV1;
  const start = "<!-- old-russia-export:v1 -->";
  const end = "<!-- /old-russia-export:v1 -->";
  function clean(source) {
    return source.replace(/<!-- old-russia-export:v1 -->[\s\S]*?<!-- \/old-russia-export:v1 -->\n?/g, "")
      .replace(/^[ \t]*@import url\("https:\/\/fonts\.googleapis\.com\/[^\n]*\);\n?/gm, "");
  }
  if (typeof module !== "undefined" && module.exports) {
    const fs = require("fs"), path = require("path"), crypto = require("crypto");
    const files = ["index.html", "old-russia/index.html",
      ...Object.values(manifest.files).map(name => "old-russia/" + name)];
    function checkPaths(root, names) {
      if (fs.lstatSync(root).isSymbolicLink()) throw Error("Unsafe Old Russia root symlink");
      for (const name of names) {
        const parts = name.split("/");
        if (path.isAbsolute(name) || parts.includes("..")) throw Error("Unsafe Old Russia path");
        let current = root;
        parts.forEach((part, index) => {
          current = path.join(current, part);
          let entry;
          try { entry = fs.lstatSync(current); }
          catch (error) { if (error.code === "ENOENT") return; throw error; }
          if (entry.isSymbolicLink()) throw Error("Unsafe Old Russia symlink leaf or ancestor");
          if (index < parts.length - 1 ? !entry.isDirectory() : !entry.isFile()) {
            throw Error("Unsafe Old Russia path type");
          }
        });
      }
    }
    const hash = value => crypto.createHash("sha256").update(value).digest("hex");
    function read(root, name) {
      const target = path.join(root, name);
      if (fs.lstatSync(target).isSymbolicLink() || fs.statSync(target).size > 2000000) {
        throw Error("Unsafe Old Russia input");
      }
      return fs.readFileSync(target, "utf8");
    }
    function preflight(root) {
      checkPaths(root, [...files, "build_old_russia_pages.js", "old_russia_export_client.js",
        ...Object.keys(manifest.source_hashes)]);
      for (const [name, checksum] of Object.entries(manifest.source_hashes)) {
        if (hash(read(root, name)) !== checksum) {
          throw Error("Old Russia source changed; rerun the explicit Python bridge");
        }
      }
      if (hash(clean(read(root, "index.html"))) !== manifest.overview_hash) {
        throw Error("Old Russia overview changed; rerun the explicit Python bridge");
      }
    }
    module.exports.preflight = preflight;
    module.exports.install = function (root) {
      preflight(root);
      const outputs = files.map(name => {
        const source = clean(read(root, name));
        if (source.split("</body>").length !== 2) throw Error("Invalid Old Russia page");
        const slug = Object.keys(manifest.files).find(key => name === "old-russia/" + manifest.files[key]) || "";
        const prefix = name.startsWith("old-russia/") ? "../" : "";
        const block = `${start}\n<script src="${prefix}old_russia_export_client.js" data-old-russia-card="${slug}"></script>\n${end}\n`;
        return [name, source.replace("</body>", block + "</body>")];
      });
      for (const [name, source] of outputs) fs.writeFileSync(path.join(root, name), source, "utf8");
    };
    return;
  }

  const script = document.currentScript || document.querySelector("script[data-old-russia-card]");
  const currentSlug = script ? script.dataset.oldRussiaCard : "";
  const clone = value => JSON.parse(JSON.stringify(value));
  const toolbar = document.createElement("div");
  toolbar.style.cssText = "padding:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:#fffdf7;color:#24231f;border:1px solid #8f8a7e;margin:12px;border-radius:8px;font:14px Arial,sans-serif";
  const status = document.createElement("span");
  status.setAttribute("role", "alert");
  const hint = document.createElement("span");
  hint.textContent = "JSON v1: текущее состояние этой страницы; остальные карточки — исходные.";
  function button(label, mode, slug) {
    const node = document.createElement("button");
    node.type = "button";
    node.textContent = label;
    node.dataset.oldRussiaExport = mode;
    if (slug) node.dataset.oldRussiaSlug = slug;
    node.style.cssText = "padding:8px 12px;cursor:pointer;font:inherit";
    return node;
  }
  if (currentSlug) toolbar.append(button("Скачать JSON карточки", "single", currentSlug));
  toolbar.append(button("Скачать все 22 карточки JSON", "batch"), hint, status);
  if (!currentSlug && document.querySelector("a.card[href]")) {
    const select = document.createElement("select");
    select.setAttribute("aria-label", "Карточка для JSON экспорта");
    manifest.document.cards.forEach(card => {
      const option = document.createElement("option");
      option.value = card.external_key.slice("old-russia:".length);
      option.textContent = card.name; select.append(option);
    });
    const single = button("Скачать JSON выбранной карточки", "single", select.value);
    select.addEventListener("change", () => { single.dataset.oldRussiaSlug = select.value; });
    toolbar.prepend(select, single);
  }
  document.body.prepend(toolbar);

  const integer = (value, maximum) => {
    if (!/^[0-9]+$/.test(String(value).trim())) throw Error("Некорректное числовое состояние HP / использований.");
    const number = Number(value);
    if (!Number.isSafeInteger(number) || number < 0 || number > maximum) throw Error("Состояние выходит за допустимый диапазон.");
    return number;
  };
  function overlay(cards) {
    if (currentSlug) {
      const card = cards.find(item => item.external_key === "old-russia:" + currentSlug);
      if (!card) throw Error("Карточка отсутствует в пакете.");
      const hp = document.querySelector(".hp-val"), max = document.querySelector(".hp-max");
      if (card.resources.some(resource => resource.key === "hp")) {
        if (!hp || !max) throw Error("На странице отсутствует состояние здоровья.");
        const resource = card.resources.find(item => item.key === "hp");
        const maximum = integer(max.textContent, 1000000000);
        if (maximum !== resource.max) throw Error("Максимум HP отличается от исходного. Повторите сборку экспорта.");
        resource.current = integer(hp.textContent, maximum);
      }
      const skills = [...document.querySelectorAll(".skill")];
      if (skills.length !== card.skills.length) throw Error("Список навыков отличается от исходного.");
      skills.forEach((node, index) => {
        const dot = node.querySelector(".skill-dot");
        if (!dot) throw Error("На странице отсутствует отметка владения.");
        card.skills[index].proficient = dot.classList.contains("proficient");
      });
      const abilities = [...document.querySelectorAll(".inv-item")].filter(node => node.querySelector(".ability-name"));
      abilities.push(...document.querySelectorAll(".ulta-card"));
      const rich = card.kind === "player_character";
      // Hero rich abilities precede overview descriptions. Other pages have one action list.
      const expected = rich ? card.abilities.filter(item => item.action_type !== "Действия / улики (overview)") : card.abilities;
      if (abilities.length !== expected.length) throw Error("Список способностей отличается от исходного.");
      abilities.forEach((node, index) => {
        const pips = [...node.querySelectorAll(".use-pip")], uses = expected[index].uses;
        if (uses) {
          if (pips.length !== uses.max) throw Error("Количество использований отличается от исходного.");
          uses.current = pips.filter(pip => !pip.classList.contains("spent")).length;
        } else if (pips.length) throw Error("Неизвестный счётчик использований.");
      });
    } else {
      // Read only visible overview cards. Never read arbitrary localStorage or another page.
      document.querySelectorAll("article.card[data-type]").forEach(node => {
        const card = cards.find(item => item.external_key === "old-russia:" + node.id);
        const hp = node.querySelector(".hpbar");
        if (card && hp) {
          const resource = card.resources.find(item => item.key === "hp");
          const parts = hp.getAttribute("title").split("/");
          if (!resource || parts.length !== 2 || integer(parts[1], 1000000000) !== resource.max) throw Error("Некорректное состояние HP на обзоре.");
          resource.current = integer(parts[0], resource.max);
        }
      });
    }
    return cards;
  }
  function addSingles() {
    document.querySelectorAll("article.card[data-type]").forEach(node => {
      if (!node.querySelector("[data-old-russia-export]")) node.append(button("Скачать JSON", "single", node.id));
    });

  }
  document.addEventListener("click", event => {
    const target = event.target.closest("[data-old-russia-export]");
    if (!target) return;
    event.preventDefault();
    try {
      const cards = overlay(clone(manifest.document.cards));
      const single = target.dataset.oldRussiaExport === "single";
      const slug = target.dataset.oldRussiaSlug;
      const value = single ? cards.find(card => card.external_key === "old-russia:" + slug) : {schema_version: 1, cards};
      if (!value) throw Error("Карточка отсутствует в пакете.");
      const json = JSON.stringify(value, null, 2) + "\n";
      const blob = new Blob([json], {type: "application/json;charset=utf-8"});
      const url = URL.createObjectURL(blob), anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = single ? slug + ".json" : "old-russia-v1.json";
      document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = single ? "JSON карточки скачан." : "Пакет из 22 карточек скачан.";
    } catch (error) {
      status.textContent = "Экспорт остановлен: " + error.message;
    }
  });
  addSingles();
  const content = document.getElementById("content");
  if (content) new MutationObserver(addSingles).observe(content, {childList: true, subtree: true});
})();
