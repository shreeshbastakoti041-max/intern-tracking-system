/* OSP Intern Tracker — small progressive enhancements. Everything works without JS. */
(function () {
  "use strict";

  /* Client-side sorting for tables marked .sortable (whole data set on the page). */
  function cellValue(cell, type) {
    var raw = cell.getAttribute("data-value");
    if (raw === null) raw = cell.textContent.trim();
    if (type === "num") {
      var n = parseFloat(raw.replace(/[^0-9.\-]/g, ""));
      return isNaN(n) ? 0 : n;
    }
    return raw.toLowerCase();
  }

  function makeSortable(table) {
    var headers = table.querySelectorAll("thead th[data-sort]");
    var body = table.tBodies[0];
    if (!body) return;
    headers.forEach(function (th) {
      var index = Array.prototype.indexOf.call(th.parentNode.children, th);
      var type = th.getAttribute("data-sort");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "sort";
      while (th.firstChild) button.appendChild(th.firstChild);
      th.appendChild(button);
      button.addEventListener("click", function () {
        var ascending = th.getAttribute("aria-sort") !== "ascending";
        if (!th.hasAttribute("aria-sort") && type === "num") ascending = false; // numbers: largest first
        headers.forEach(function (h) { h.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        var rows = Array.prototype.filter.call(body.rows, function (r) { return !r.hasAttribute("data-fixed"); });
        rows.sort(function (a, b) {
          var x = cellValue(a.children[index], type), y = cellValue(b.children[index], type);
          if (x < y) return ascending ? -1 : 1;
          if (x > y) return ascending ? 1 : -1;
          return 0;
        });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  }

  /* In-cell bars: width relative to the largest value in the same table and group. */
  function drawBars(scope) {
    var groups = {};
    scope.querySelectorAll("[data-bar]").forEach(function (el) {
      var key = el.getAttribute("data-bar-group") || "default";
      (groups[key] = groups[key] || []).push(el);
    });
    Object.keys(groups).forEach(function (key) {
      var els = groups[key];
      var max = Math.max.apply(null, els.map(function (el) { return parseFloat(el.getAttribute("data-bar")) || 0; }));
      els.forEach(function (el) {
        var v = parseFloat(el.getAttribute("data-bar")) || 0;
        var fill = el.querySelector("span");
        if (fill) fill.style.width = (max > 0 ? (v / max) * 100 : 0).toFixed(1) + "%";
      });
    });
  }

  /* Live hours preview in the entry form. */
  function hoursPreview(form) {
    var out = form.querySelector("[data-hours]");
    var start = form.querySelector("[name=start_time]");
    var end = form.querySelector("[name=end_time]");
    if (!out || !start || !end) return;
    function minutes(v) { var p = (v || "").split(":"); return p.length < 2 ? null : (+p[0]) * 60 + (+p[1]); }
    function update() {
      var s = minutes(start.value), e = minutes(end.value);
      out.style.color = "";
      if (s === null || e === null) { out.textContent = "0.00"; return; }
      if (e <= s) { out.textContent = "End must be after start"; out.style.color = "var(--error)"; return; }
      out.textContent = ((e - s) / 60).toFixed(2);
    }
    start.addEventListener("input", update);
    end.addEventListener("input", update);
    update();
  }

  /* Period toolbar: choosing a range applies it; typing dates switches to a custom range. */
  function periodBar(form) {
    var select = form.querySelector("select[name=period]");
    var dates = form.querySelectorAll("input[type=date]");
    if (!select) return;
    select.addEventListener("change", function () {
      if (select.value) dates.forEach(function (d) { d.value = ""; });
      if (select.value) form.submit();
    });
    dates.forEach(function (d) { d.addEventListener("input", function () { select.value = ""; }); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("table.sortable").forEach(makeSortable);
    drawBars(document);
    document.querySelectorAll("form[data-entry-form]").forEach(hoursPreview);
    document.querySelectorAll("form.periodbar").forEach(periodBar);
  });
})();
