const API = "http://127.0.0.1:8000/api/test-score";

const sampleTransactions = [
  { date: "2024-01-01", amount: 50000, category: "salary", balance: 50000 },
  { date: "2024-01-05", amount: -12000, category: "rent", balance: 38000 },
  { date: "2024-01-10", amount: -3000, category: "groceries", balance: 35000 },
  { date: "2024-01-15", amount: -1500, category: "food", balance: 33500 },
  { date: "2024-01-20", amount: -2000, category: "transport", balance: 31500 },
  { date: "2024-01-25", amount: -1000, category: "entertainment", balance: 30500 },
  { date: "2024-02-01", amount: 50000, category: "salary", balance: 80500 },
  { date: "2024-02-05", amount: -12000, category: "rent", balance: 68500 },
  { date: "2024-02-10", amount: -3500, category: "groceries", balance: 65000 },
  { date: "2024-02-15", amount: -2000, category: "food", balance: 63000 },
  { date: "2024-02-20", amount: -2000, category: "transport", balance: 61000 },
  { date: "2024-02-25", amount: -5000, category: "entertainment", balance: 56000 }
];

const dom = {
  sampleBtn: document.getElementById("sampleBtn"),
  uploadBtn: document.getElementById("uploadBtn"),
  pdfInput: document.getElementById("pdfInput"),
  loading: document.getElementById("loadingSection"),
  dashboard: document.getElementById("dashboardSection"),
  score: document.getElementById("creditScoreValue"),
  message: document.getElementById("scoreMessage"),
  features: document.getElementById("featuresGrid"),
  insights: document.getElementById("insightsList"),
  chart: document.getElementById("factorChart"),
  adviceBox: document.getElementById("adviceBox"),
  occupationInput: document.getElementById("occupationInput"),
  pdfPassword: document.getElementById("pdfPassword")
};

let chart = null;

function showLoading(state) {
  dom.loading.classList.toggle("hidden", !state);
  if (state) {
    dom.loading.querySelector("p").textContent = "Processing your bank statement...";
  }
}

function renderFeatures(features) {
  dom.features.innerHTML = "";

  Object.entries(features).forEach(([k, v]) => {
    const card = document.createElement("div");
    card.className = "feature-card";
    card.innerHTML = `
      <p class="feature-key">${k.replaceAll("_", " ")}</p>
      <p class="feature-value">${typeof v === "number" ? v.toFixed(2) : v}</p>
    `;
    dom.features.appendChild(card);
  });
}

function renderInsights(data) {
  const features = data.features;
  const score = data.score.credit_score;

  const items = [];

  if (score > 700) items.push("Strong financial profile");
  else if (score > 550) items.push("Moderate financial stability");
  else items.push("High financial risk");

  if ((features.savings_ratio ?? 0) > 0)
    items.push("Positive savings behavior");
  else
    items.push("Low or negative savings");

  dom.insights.innerHTML = items
    .map(i => `<li>${i}</li>`)
    .join("");
}

function renderChart(data) {
  if (!dom.chart) return;

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
  const { features, score, advice } = data;

  dom.score.textContent = score.credit_score;
  dom.message.textContent = score.message;

  if (dom.adviceBox) {
    dom.adviceBox.textContent = advice || "No advice available.";
  }

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
  formData.append("occupation", dom.occupationInput.value || "Other");
  formData.append("password", dom.pdfPassword.value || "");

  showLoading(true);

  try {
    const res = await fetch("http://127.0.0.1:8000/api/analyze", {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errorData.detail || `HTTP ${res.status}: ${res.statusText}`);
    }

    const data = await res.json();
    renderDashboard(data);

  } catch (error) {
    alert("PDF Upload Failed: " + error.message);
    console.error("Upload error:", error);
  }

  showLoading(false);
};

dom.sampleBtn.onclick = handleSample;