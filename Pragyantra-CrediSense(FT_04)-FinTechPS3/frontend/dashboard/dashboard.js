const API = "http://127.0.0.1:8000/api/test-score";

const sampleTransactions = [
  { date: "2024-01-01", amount: 50000, category: "salary", balance: 50000 },
  { date: "2024-01-05", amount: -12000, category: "rent", balance: 38000 },
  { date: "2024-01-10", amount: -3000, category: "groceries", balance: 35000 }
];

const dom = {
  sampleBtn: document.getElementById("sampleBtn"),
  uploadBtn: document.getElementById("uploadBtn"),
  pdfInput: document.getElementById("pdfInput"),
  loading: document.getElementById("loading"),
  dashboard: document.getElementById("dashboard"),
  score: document.getElementById("score"),
  message: document.getElementById("message"),
  features: document.getElementById("features"),
  insights: document.getElementById("insights"),
  chart: document.getElementById("chart")
};

let chart = null;

function showLoading(state) {
  dom.loading.classList.toggle("hidden", !state);
}

function renderFeatures(features) {
  dom.features.innerHTML = "";

  Object.entries(features).forEach(([k, v]) => {
    const div = document.createElement("div");

    div.className =
      "bg-slate-800 p-3 rounded-lg text-sm flex justify-between";

    div.innerHTML = `
      <span class="text-gray-400">${k.replaceAll("_", " ")}</span>
      <span class="font-semibold">${v}</span>
    `;

    dom.features.appendChild(div);
  });
}

function renderInsights(data) {
  const f = data.features;
  const score = data.score.credit_score;

  const insights = [];

  if (score > 700) insights.push("Excellent credit profile");
  else insights.push("Needs improvement");

  if (f.savings_ratio > 0.2) insights.push("Good savings habit");
  else insights.push("Low savings");

  if (f.overdraft_frequency < 0.1) insights.push("Low overdraft risk");
  else insights.push("Frequent overdrafts");

  dom.insights.innerHTML = insights.map(i => `<li>${i}</li>`).join("");
}

function renderChart(data) {
  if (chart) chart.destroy();

  chart = new Chart(dom.chart, {
    type: "bar",
    data: {
      labels: Object.keys(data).map(k => k.replaceAll("_", " ")),
      datasets: [{
        data: Object.values(data),
        backgroundColor: "#6366f1"
      }]
    }
  });
}

function renderDashboard(data) {
  const { features, score } = data;

  dom.score.innerText = score.credit_score;
  dom.message.innerText = score.message;

  renderFeatures(features);
  renderInsights(data);
  renderChart(score.factor_breakdown);

  dom.dashboard.classList.remove("hidden");
}

async function fetchScore(payload) {
  const res = await fetch(API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  return res.json();
}

async function handleSample() {
  showLoading(true);

  try {
    const data = await fetchScore({
      transactions: sampleTransactions,
      occupation: "Student"
    });

    renderDashboard(data);

  } catch (e) {
    alert("Backend error");
    console.error(e);
  }

  showLoading(false);
}

dom.uploadBtn.onclick = () => dom.pdfInput.click();

dom.pdfInput.onchange = async (e) => {
  const file = e.target.files[0];

  const formData = new FormData();
  formData.append("file", file);

  showLoading(true);

  try {
    const res = await fetch("http://127.0.0.1:8000/api/upload", {
      method: "POST",
      body: formData
    });

    const data = await res.json();
    renderDashboard(data);

  } catch {
    alert("Upload failed");
  }

  showLoading(false);
};

dom.sampleBtn.onclick = handleSample;