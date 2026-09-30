/* Excel-style autofilter for the packet's larger tables (#32), inlined in
   the page so it works offline. Each column header gets a button opening a
   panel: sort A to Z / Z to A, a search box, (Select all) and a checklist
   of the column's values. Filters on several columns combine, and a quick
   search box above the table matches words anywhere in a row. Screen only:
   print hides the controls and shows every row in the original order.
   Without JavaScript the tables are plain. MIN_ROWS is set by the page. */
(function () {
  'use strict';

  var BLANK = '(Blanks)';
  var openPanel = null;

  function text(cell) {
    return (cell ? cell.textContent : '').trim();
  }

  // Numbers and IP addresses compare by value ("9" before "10",
  // "192.168.2.9" before "192.168.2.10"), everything else alphabetically
  var collator = new Intl.Collator(undefined, {numeric: true,
                                                sensitivity: 'base'});
  function compare(a, b) {
    if (a === b) return 0;
    if (a === '') return 1;           // blanks last
    if (b === '') return -1;
    return collator.compare(a, b);
  }

  function setup(table) {
    var body = table.tBodies[0];
    var head = table.tHead;
    if (!body || !head || body.rows.length <= MIN_ROWS) return;
    var headers = head.rows[0].cells;
    var rows = Array.prototype.slice.call(body.rows);
    var original = rows.slice();
    var filters = {};                 // column -> {value: true} allowed
    var sortState = null;             // {col, dir}
    var words = [];

    // Quick search and count, above the table
    var bar = document.createElement('div');
    bar.className = 'table-filter';
    var search = document.createElement('input');
    search.type = 'search';
    search.placeholder = 'Filter this table';
    search.setAttribute('aria-label', 'Filter this table');
    var count = document.createElement('span');
    count.className = 'table-filter-count';
    var clear = document.createElement('button');
    clear.type = 'button';
    clear.textContent = 'Clear filters';
    clear.hidden = true;
    bar.appendChild(search);
    bar.appendChild(count);
    bar.appendChild(clear);
    table.parentNode.insertBefore(bar, table);

    function passes(row, skipCol) {
      var cells = row.cells;
      for (var col in filters) {
        if (+col === skipCol) continue;
        var value = text(cells[col]);
        if (!filters[col][value === '' ? BLANK : value]) return false;
      }
      if (words.length) {
        var all = row.textContent.toLowerCase();
        for (var i = 0; i < words.length; i++) {
          if (all.indexOf(words[i]) === -1) return false;
        }
      }
      return true;
    }

    function apply() {
      var shown = 0;
      rows.forEach(function (row) {
        var ok = passes(row, -1);
        row.classList.toggle('filtered-out', !ok);
        if (ok) shown++;
      });
      var active = Object.keys(filters).length > 0 || words.length > 0;
      count.textContent = active ?
        shown + ' of ' + rows.length + ' rows' : rows.length + ' rows';
      clear.hidden = !active && !sortState;
      Array.prototype.forEach.call(headers, function (th, col) {
        var button = th.querySelector('.af-button');
        var on = filters.hasOwnProperty(col);
        button.classList.toggle('af-active', on);
        button.textContent = on ? '\u25BC' : '\u25BE';
        button.setAttribute('aria-pressed', on ? 'true' : 'false');
        th.classList.toggle('af-sorted-asc',
                            !!sortState && sortState.col === col &&
                            sortState.dir === 1);
        th.classList.toggle('af-sorted-desc',
                            !!sortState && sortState.col === col &&
                            sortState.dir === -1);
      });
    }

    function order(list) {
      list.forEach(function (row) { body.appendChild(row); });
    }

    function sort(col, dir) {
      sortState = {col: col, dir: dir};
      var sorted = original.slice().sort(function (a, b) {
        return dir * compare(text(a.cells[col]), text(b.cells[col]));
      });
      order(sorted);
      apply();
    }

    search.addEventListener('input', function () {
      words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
      apply();
    });
    clear.addEventListener('click', function () {
      filters = {};
      words = [];
      search.value = '';
      sortState = null;
      order(original);
      apply();
    });

    // Print: every row, original order; screen state comes back after
    window.addEventListener('beforeprint', function () { order(original); });
    window.addEventListener('afterprint', function () {
      if (sortState) sort(sortState.col, sortState.dir);
    });

    Array.prototype.forEach.call(headers, function (th, col) {
      var name = text(th);
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'af-button';
      button.setAttribute('aria-label', 'Filter or sort ' + name);
      button.setAttribute('aria-haspopup', 'dialog');
      th.appendChild(button);
      button.addEventListener('click', function (event) {
        event.stopPropagation();
        if (openPanel && openPanel.button === button) {
          closePanel();
        } else {
          showPanel(col, name, button);
        }
      });
    });

    function showPanel(col, name, button) {
      closePanel();
      // The values left once the other columns' filters apply, as in Excel
      var seen = {};
      rows.forEach(function (row) {
        if (!passes(row, col)) return;
        var value = text(row.cells[col]);
        seen[value === '' ? BLANK : value] = true;
      });
      var values = Object.keys(seen).sort(function (a, b) {
        return compare(a === BLANK ? '' : a, b === BLANK ? '' : b);
      });
      var chosen = {};
      values.forEach(function (v) {
        chosen[v] = !filters[col] || !!filters[col][v];
      });

      var panel = document.createElement('div');
      panel.className = 'af-panel';
      panel.setAttribute('role', 'dialog');
      panel.setAttribute('aria-label', 'Filter ' + name);

      function action(label, handler) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'af-action';
        b.textContent = label;
        b.addEventListener('click', handler);
        panel.appendChild(b);
        return b;
      }
      var first = action('Sort A to Z', function () {
        sort(col, 1); closePanel();
      });
      action('Sort Z to A', function () { sort(col, -1); closePanel(); });
      action('Clear filter from "' + name + '"', function () {
        delete filters[col]; apply(); closePanel();
      }).disabled = !filters[col];

      var find = document.createElement('input');
      find.type = 'search';
      find.placeholder = 'Search';
      find.setAttribute('aria-label', 'Search the values of ' + name);
      panel.appendChild(find);

      var list = document.createElement('div');
      list.className = 'af-list';
      panel.appendChild(list);

      var allBox;
      var boxes = [];
      function checkbox(label, checked, onChange) {
        var row = document.createElement('label');
        var box = document.createElement('input');
        box.type = 'checkbox';
        box.checked = checked;
        box.addEventListener('change', onChange);
        row.appendChild(box);
        row.appendChild(document.createTextNode(' ' + label));
        list.appendChild(row);
        return box;
      }
      function visibleValues() {
        var needle = find.value.toLowerCase();
        return values.filter(function (v) {
          return v.toLowerCase().indexOf(needle) !== -1;
        });
      }
      function syncAll() {
        var shown = visibleValues();
        var on = shown.filter(function (v) { return chosen[v]; }).length;
        allBox.checked = on === shown.length && on > 0;
        allBox.indeterminate = on > 0 && on < shown.length;
      }
      allBox = checkbox('(Select all)', true, function () {
        visibleValues().forEach(function (v) { chosen[v] = allBox.checked; });
        boxes.forEach(function (b) { b.box.checked = chosen[b.value]; });
      });
      values.forEach(function (v) {
        var box = checkbox(v, chosen[v], function () {
          chosen[v] = box.checked;
          syncAll();
        });
        boxes.push({value: v, box: box, row: box.parentNode});
      });
      syncAll();
      find.addEventListener('input', function () {
        var shown = visibleValues();
        boxes.forEach(function (b) {
          b.row.hidden = shown.indexOf(b.value) === -1;
        });
        syncAll();
      });

      var buttons = document.createElement('div');
      buttons.className = 'af-buttons';
      panel.appendChild(buttons);
      var ok = document.createElement('button');
      ok.type = 'button';
      ok.textContent = 'OK';
      var cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.textContent = 'Cancel';
      buttons.appendChild(ok);
      buttons.appendChild(cancel);
      ok.addEventListener('click', function () {
        // A search narrows the choice to the matching values, as in Excel
        var shown = find.value ? visibleValues() : values;
        var allowed = {};
        var all = true;
        values.forEach(function (v) {
          var keep = chosen[v] && shown.indexOf(v) !== -1;
          if (keep) allowed[v] = true;
          else all = false;
        });
        if (all) delete filters[col];
        else filters[col] = allowed;
        apply();
        closePanel();
      });
      cancel.addEventListener('click', closePanel);
      panel.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { closePanel(); button.focus(); }
        if (event.key === 'Enter' && event.target.type !== 'button') {
          ok.click();
        }
      });
      panel.addEventListener('click', function (event) {
        event.stopPropagation();
      });

      document.body.appendChild(panel);
      var rect = button.getBoundingClientRect();
      var left = Math.min(rect.left, window.innerWidth - panel.offsetWidth - 8);
      panel.style.left = Math.max(8, left) + 'px';
      panel.style.top = (rect.bottom + 4) + 'px';
      openPanel = {panel: panel, button: button};
      button.setAttribute('aria-expanded', 'true');
      first.focus();
    }

    apply();
  }

  function closePanel() {
    if (!openPanel) return;
    openPanel.button.setAttribute('aria-expanded', 'false');
    openPanel.panel.remove();
    openPanel = null;
  }

  // Close the panel on anything outside it: a click elsewhere, or the page
  // scrolling (it's fixed in place, so it would drift from its button).
  // What happens inside it (scrolling the value list, dragging its
  // scrollbar, selecting text in its search box) must not close it.
  function inPanel(event) {
    return openPanel && event.target instanceof Node &&
      (openPanel.panel.contains(event.target) ||
       openPanel.button.contains(event.target));
  }
  document.addEventListener('mousedown', function (event) {
    if (!inPanel(event)) closePanel();
  });
  window.addEventListener('scroll', function (event) {
    if (!inPanel(event)) closePanel();
  }, true);
  window.addEventListener('resize', closePanel);
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closePanel();
  });

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(document.querySelectorAll('table'), setup);
  });
})();
