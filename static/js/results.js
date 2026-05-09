/* Results dashboard — polls /results/data and re-renders chart + table. */
(function () {
  const ctx = document.getElementById("chart").getContext("2d");
  const tbody = document.querySelector("#results-table tbody");

  const NAVY = "#1E3A8A";
  const NAVY_LIGHT = "#DBEAFE";

  let chart = new Chart(ctx, {
    type: "bar",
    data: { labels: [], datasets: [{ label: "Votes", data: [], backgroundColor: NAVY, borderRadius: 8 }] },
    options: {
      responsive: true,
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 } },
        y: { ticks: { color: "#0F172A", font: { weight: 600 } } },
      },
    },
  });

  function setText(id, value) { document.getElementById(id).textContent = value; }

  async function refresh() {
    try {
      const res = await fetch("/results/data");
      const data = await res.json();

      setText("s-registered", data.total_voters);
      setText("s-voted", data.total_voted);
      setText("s-turnout", data.turnout + "%");
      setText("s-last", data.last_vote ? data.last_vote.replace("T", " ") : "—");

      const labels = data.candidates.map((c) => `${c.name} (${c.party})`);
      const counts = data.candidates.map((c) => c.votes);
      chart.data.labels = labels;
      chart.data.datasets[0].data = counts;
      chart.data.datasets[0].backgroundColor = counts.map((_, i) => i === 0 && counts[0] > 0 ? NAVY : NAVY_LIGHT);
      chart.update();

      tbody.innerHTML = data.candidates.map((c, i) => `
        <tr>
          <td>${i + 1}</td>
          <td>${c.name}</td>
          <td>${c.party}</td>
          <td class="num"><strong>${c.votes}</strong></td>
        </tr>`).join("") || `<tr><td colspan="4" class="empty">No candidates yet.</td></tr>`;
    } catch (err) {
      console.error("results fetch failed", err);
    }
  }

  refresh();
  setInterval(refresh, 3000);
})();
