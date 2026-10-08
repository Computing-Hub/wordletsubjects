// Term form: new-topic box, extra question blocks and the live preview.
(() => {
  const $ = id => document.getElementById(id);
  const form = $("termForm");
  if (!form) return;

  // "New topic…" shows a text box.
  const topic = $("topic"), newTopic = $("new_topic");
  if (topic && newTopic) {
    topic.addEventListener("change", () => {
      newTopic.hidden = topic.value !== "__new__";
      if (!newTopic.hidden) newTopic.focus();
    });
  }

  // Extra follow-up blocks.
  const blocks = [...form.querySelectorAll("fieldset.fu")];
  const addBtn = $("addFu");
  const syncAdd = () => { addBtn.hidden = blocks.every(b => !b.hidden); };
  addBtn.addEventListener("click", () => {
    const next = blocks.find(b => b.hidden);
    if (next) { next.hidden = false; next.querySelector("textarea").focus(); current = next; preview(); }
    syncAdd();
  });
  form.querySelectorAll(".removeFu").forEach(btn => btn.addEventListener("click", () => {
    const b = btn.closest("fieldset");
    b.querySelectorAll("input,textarea").forEach(el => { el.value = ""; });
    b.hidden = true;
    if (current === b) current = blocks[0];
    syncAdd(); preview();
  }));
  syncAdd();

  // Preview: the tiles as they'd look once solved, plus the question being edited.
  let current = blocks[0];
  form.addEventListener("focusin", e => {
    const b = e.target.closest("fieldset.fu");
    if (b) { current = b; preview(); }
  });

  function tiles(term) {
    const box = $("pvTiles");
    if (!box) return;
    const upper = term.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
    const letters = upper.replace(/[^A-Z]/g, "");
    box.innerHTML = "";
    let pos = 0;
    for (const ch of upper) {
      if (/[A-Z]/.test(ch)) {
        const s = document.createElement("span");
        s.className = "c"; s.textContent = ch; box.appendChild(s); pos++;
      } else if (pos > 0 && box.lastChild) {
        box.lastChild.classList.add("gap");
      }
    }
    const words = upper.split(/[^A-Z]+/).filter(Boolean).length;
    const accents = /[̀-ͯ]/.test(term.normalize("NFD"));
    $("pvMeta").textContent = letters.length
      ? `${letters.length} letters${words > 1 ? `, ${words} words` : ""}, ${letters.length <= 6 ? 5 : 6} guesses` +
        (accents ? ". No accents needed" : "") + (letters.length > 30 ? ". Too long!" : "")
      : "";
  }

  function preview() {
    const term = (form.elements.term && form.elements.term.value) || "";
    const clue = $("clue");
    if (clue) {
      $("pvClue").textContent = clue.value.trim() || "The clue appears here.";
      $("pvClue").classList.toggle("muted", !clue.value.trim());
      tiles(term);
    }
    const n = current.dataset.n;
    const v = name => (form.elements[`${name}_${n}`] || {}).value || "";
    $("pvQ").textContent = v("question").trim() || "The follow-up question appears here.";
    const box = $("pvOpts");
    box.innerHTML = "";
    ["correct_answer", "wrong_1", "wrong_2", "wrong_3"].forEach((f, i) => {
      const text = v(f).trim();
      if (!text) return;
      const d = document.createElement("div");
      d.textContent = text;
      if (i === 0) d.className = "right";
      box.appendChild(d);
    });
    $("pvExp").textContent = v("explanation").trim();
  }
  form.addEventListener("input", preview);
  form.addEventListener("change", preview);
  preview();
})();
