// Code-to-name list, kept only in this browser (localStorage). Never sent to the server.
(() => {
  const KEY = "kt-names-" + window.KT_CLASS;
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } };
  const save = names => { try { localStorage.setItem(KEY, JSON.stringify(names)); return true; } catch (e) { return false; } };
  const cells = () => [...document.querySelectorAll("[data-code]")];
  const codes = () => [...new Set(cells().map(el => el.dataset.code))];

  function render() {
    const names = load();
    cells().forEach(el => {
      const code = el.dataset.code, name = names[code];
      if (el.classList.contains("name")) { el.textContent = name || ""; return; }
      el.textContent = "";
      if (name) {
        el.append(name);
        const s = document.createElement("small"); s.textContent = code; el.appendChild(s);
      } else {
        el.textContent = code;
      }
    });
  }

  const dlg = document.getElementById("namesDlg");
  const list = document.getElementById("namesList");
  const open = document.getElementById("editNames");
  if (dlg && open) {
    open.addEventListener("click", () => {
      const names = load();
      list.innerHTML = "";
      codes().forEach(code => {
        const row = document.createElement("label");
        row.className = "row"; row.style.margin = "0";
        const c = document.createElement("span");
        c.textContent = code; c.style.cssText = "width:90px;font-family:ui-monospace,Menlo,monospace;font-weight:700";
        const input = document.createElement("input");
        input.type = "text"; input.value = names[code] || "";
        input.setAttribute("data-for", code); input.maxLength = 60; input.style.flex = "1"; input.style.width = "auto";
        input.autocomplete = "off";
        row.append(c, input);
        list.appendChild(row);
      });
      dlg.showModal();
      const first = list.querySelector("input"); if (first) first.focus();
    });
    document.getElementById("closeNames").addEventListener("click", () => dlg.close());
    document.getElementById("saveNames").addEventListener("click", () => {
      const names = {};
      list.querySelectorAll("input[data-for]").forEach(i => { if (i.value.trim()) names[i.dataset.for] = i.value.trim(); });
      if (!save(names)) alert("This browser won't let the page save names (private browsing?).");
      dlg.close(); render();
    });
    document.getElementById("clearNames").addEventListener("click", () => {
      if (!confirm("Remove all names for this class from this computer?")) return;
      try { localStorage.removeItem(KEY); } catch (e) {}
      dlg.close(); render();
    });
  }
  render();
})();
