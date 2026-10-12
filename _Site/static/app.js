// Filtros de Personajes y pestañas de planos. Sin dependencias.
(function () {
  function norm(s) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }

  var grid = document.getElementById("grid");
  if (grid) {
    var tiles = Array.prototype.slice.call(grid.querySelectorAll(".tile"));
    var q = document.getElementById("q");
    var chips = Array.prototype.slice.call(document.querySelectorAll(".chip"));
    var count = document.getElementById("count");
    var empty = document.getElementById("empty");
    var group = "";

    function apply() {
      var term = norm(q.value.trim()), shown = 0;
      tiles.forEach(function (t) {
        var okGroup = !group || t.dataset.groups.split(" ").indexOf(group) !== -1;
        var okText = !term || t.dataset.text.indexOf(term) !== -1;
        var ok = okGroup && okText;
        t.hidden = !ok;
        if (ok) shown++;
      });
      count.textContent = shown === tiles.length ? tiles.length + " personajes"
        : "Mostrando " + shown + " de " + tiles.length;
      empty.hidden = shown !== 0;
    }
    function setGroup(g) {
      group = g;
      chips.forEach(function (c) { c.setAttribute("aria-pressed", String(c.dataset.group === g)); });
      apply();
    }
    chips.forEach(function (c) { c.addEventListener("click", function () { setGroup(c.dataset.group); }); });
    q.addEventListener("input", apply);
    var fromHash = decodeURIComponent(location.hash.slice(1));
    setGroup(chips.some(function (c) { return c.dataset.group === fromHash; }) ? fromHash : "");
  }

  var plans = document.getElementById("plans");
  if (plans) {
    var figs = Array.prototype.slice.call(plans.querySelectorAll(".plan"));
    var tabs = document.createElement("div");
    tabs.className = "tabs";
    tabs.setAttribute("role", "group");
    tabs.setAttribute("aria-label", "Elegir planta");
    figs.forEach(function (f, i) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "chip br"; b.textContent = f.dataset.label;
      b.addEventListener("click", function () { show(i); });
      tabs.appendChild(b);
    });
    plans.parentNode.insertBefore(tabs, plans);
    function show(n) {
      figs.forEach(function (f, i) {
        f.hidden = i !== n;
        tabs.children[i].setAttribute("aria-pressed", String(i === n));
      });
    }
    show(0);
  }
})();
