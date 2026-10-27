/* Frontend logic. The pages talk to the Flask backend through its REST API (/api/...). */
(function () {
  "use strict";

  function getJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (res) {
      if (!res.ok) { throw new Error("Request failed: " + res.status); }
      return res.json();
    });
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  /* ---------- Booking page: live train list with fares and seats left ---------- */
  function initBookingForm() {
    var form = document.getElementById("booking-form");
    var panel = document.getElementById("live-trains");
    if (!form || !panel) { return; }

    var source = form.elements.source;
    var destination = form.elements.destination;
    var date = form.elements.journey_date;
    var trainClass = form.elements.train_class;
    var passengers = form.elements.passengers;
    var trainNo = form.elements.train_no;

    function render(trains) {
      var cls = trainClass.value;
      var pax = parseInt(passengers.value, 10) || 1;
      if (!trains.length) {
        panel.innerHTML = "<p>No train runs on this route in the dataset.</p>";
        trainNo.value = "";
        return;
      }
      var html = "<h4>Trains on this route (live from the backend)</h4>";
      trains.forEach(function (t) {
        var fare = t.classes[cls];
        var left = t.seats_available ? t.seats_available[cls] : null;
        var disabled = fare === undefined || left === 0 ? " disabled" : "";
        var checked = trainNo.value === t.train_no && !disabled ? " checked" : "";
        var info = fare === undefined
          ? cls + " not available"
          : "₹" + fare + " per person · " + left + " seats left · total ₹" + (fare * pax);
        html += '<label class="live-train"><input type="radio" name="live_train" value="' +
          escapeHtml(t.train_no) + '"' + checked + disabled + "> <strong>" + escapeHtml(t.train_no) +
          " " + escapeHtml(t.name) + "</strong> " + escapeHtml(t.departure) + " → " +
          escapeHtml(t.arrival) + " (" + escapeHtml(t.duration) + ")<br><small>" + info + "</small></label>";
      });
      panel.innerHTML = html;
      if (!panel.querySelector("input:checked")) {
        var first = panel.querySelector("input:not(:disabled)");
        if (first) { first.checked = true; }
      }
      var selected = panel.querySelector("input:checked");
      trainNo.value = selected ? selected.value : "";
    }

    function refresh() {
      if (!source.value || !destination.value || source.value === destination.value || !date.value) {
        panel.hidden = true;
        return;
      }
      var url = "/api/trains?source=" + encodeURIComponent(source.value) +
        "&destination=" + encodeURIComponent(destination.value) +
        "&date=" + encodeURIComponent(date.value);
      getJSON(url).then(function (data) {
        panel.hidden = false;
        render(data.trains);
      }).catch(function () { panel.hidden = true; });
    }

    panel.addEventListener("change", function (event) {
      if (event.target.name === "live_train") { trainNo.value = event.target.value; }
    });
    [source, destination].forEach(function (el) {
      el.addEventListener("change", function () { trainNo.value = ""; refresh(); });
    });
    [date, trainClass, passengers].forEach(function (el) {
      el.addEventListener("change", refresh);
    });
    refresh();
  }

  /* ---------- View trains page: instant filtering ---------- */
  function initTrainFilter() {
    var text = document.getElementById("filter-text");
    var type = document.getElementById("filter-type");
    var counter = document.getElementById("train-count");
    if (!text || !type) { return; }
    var cards = Array.prototype.slice.call(document.querySelectorAll(".train-card[data-search]"));

    function apply() {
      var query = text.value.trim().toLowerCase();
      var wanted = type.value;
      var shown = 0;
      cards.forEach(function (card) {
        var visible = (!query || card.dataset.search.indexOf(query) !== -1) &&
                      (!wanted || card.dataset.type === wanted);
        card.hidden = !visible;
        if (visible) { shown += 1; }
      });
      if (counter) { counter.textContent = shown; }
    }
    text.addEventListener("input", apply);
    type.addEventListener("change", apply);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initBookingForm();
    initTrainFilter();
  });
})();
