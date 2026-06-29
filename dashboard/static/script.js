document.addEventListener("DOMContentLoaded", () => {
    // Start Live Clock
    setInterval(updateClock, 1000);
    updateClock();

    // Set Default Date
    const dateSelect = document.getElementById('date-select');
    const indexSelect = document.getElementById('index-select');
    dateSelect.value = new Date().toISOString().split('T')[0];

    // Initial Data Fetch
    fetchLatestData();
    fetchHistoryData();

    // Event Listeners for Filters
    dateSelect.addEventListener('change', fetchHistoryData);
    indexSelect.addEventListener('change', fetchHistoryData);

    // Auto Refresh Cards every 5 minutes (300,000 ms)
    setInterval(fetchLatestData, 300000);
});

function updateClock() {
    const now = new Date();
    document.getElementById('live-clock').innerText = now.toLocaleTimeString('en-IN');
}

function formatNumber(num) {
    return Number(num).toLocaleString('en-IN');
}

function getTrendDetails(trend) {
    if (trend === 'Increasing') return { class: 'trend-up', icon: '🟢', sign: '+' };
    if (trend === 'Decreasing') return { class: 'trend-down', icon: '🔴', sign: '' };
    return { class: 'trend-equal', icon: '⚪', sign: '' };
}

async function fetchLatestData() {
    try {
        const res = await fetch('/api/latest');
        const data = await res.json();
        
        const container = document.getElementById('latest-cards');
        container.innerHTML = '';
        let lastUpdateTime = 'N/A';

        data.forEach(item => {
            const t = getTrendDetails(item.trend_status);
            lastUpdateTime = item.date_time;

            const card = document.createElement('div');
            card.className = 'card';
            card.innerHTML = `
                <h3>${item.index_name}</h3>
                <div class="card-row"><span>Spot Price</span> <span>₹${formatNumber(item.spot || 0)}</span></div>
                <div class="card-row"><span>ATM Strike</span> <span>${formatNumber(item.atm_strike)}</span></div>
                <div class="card-row"><span>CE Δ OI</span> <span class="trend-down">${formatNumber(item.total_ce_chg_oi)}</span></div>
                <div class="card-row"><span>PE Δ OI</span> <span class="trend-up">${formatNumber(item.total_pe_chg_oi)}</span></div>
                <div class="card-row" style="margin-top: 15px; border-top: 1px solid var(--border-color); padding-top: 10px;">
                    <span>PCR</span> <span style="font-size: 16px;">${item.pcr_value.toFixed(4)}</span>
                </div>
                <div class="card-row"><span>% Change</span> <span class="${t.class}">${t.sign}${item.pcr_pct_change.toFixed(2)}%</span></div>
                <div class="card-row"><span>Trend</span> <span>${t.icon} ${item.trend_status}</span></div>
            `;
            container.appendChild(card);
        });

        document.getElementById('last-update-time').innerText = lastUpdateTime;
    } catch (error) {
        console.error("Failed to fetch latest data", error);
    }
}

async function fetchHistoryData() {
    const index = document.getElementById('index-select').value;
    const date = document.getElementById('date-select').value;
    const tbody = document.getElementById('table-body');
    const loading = document.getElementById('loading-indicator');

    tbody.innerHTML = '';
    loading.classList.remove('hidden');

    try {
        const res = await fetch(`/api/history?index=${index}&date=${date}`);
        const data = await res.json();
        loading.classList.add('hidden');

        if (data.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--text-muted);">No data available for ${index} on ${date}.</td></tr>`;
            return;
        }

        data.forEach(item => {
            const t = getTrendDetails(item.trend_status);
            const timeOnly = item.date_time.split(' ')[1];

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${timeOnly}</td>
                <td>₹${formatNumber(item.spot || 0)}</td>
                <td>${formatNumber(item.atm_strike)}</td>
                <td class="trend-down">${formatNumber(item.total_ce_chg_oi)}</td>
                <td class="trend-up">${formatNumber(item.total_pe_chg_oi)}</td>
                <td style="font-weight: bold;">${item.pcr_value.toFixed(4)}</td>
                <td class="${t.class}">${t.sign}${item.pcr_pct_change.toFixed(2)}%</td>
                <td class="${t.class}">${t.icon} ${item.trend_status}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (error) {
        loading.classList.add('hidden');
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--red);">Error loading data. Ensure backend is running.</td></tr>`;
    }
}