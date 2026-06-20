/**
 * THEIA · 图表渲染模块
 *
 * 基于 Chart.js 绘制折线图和柱状图。
 */

/**
 * 绘制 CPI 走势图（折线图）
 * @param {HTMLCanvasElement} canvas
 * @param {object} chartData - { labels: string[], datasets: { label, data, borderColor, ... }[] }
 * @returns {Chart|null}
 */
export function renderLineChart(canvas, chartData) {
  if (!canvas || !chartData || !chartData.labels || !chartData.labels.length) {
    return null;
  }

  const ctx = canvas.getContext('2d');

  // 销毁旧图表
  if (canvas._chart) {
    canvas._chart.destroy();
  }

  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: chartData.labels,
      datasets: chartData.datasets.map(ds => ({
        ...ds,
        fill: ds.fill !== undefined ? ds.fill : false,
        tension: ds.tension || 0.3,
        pointRadius: 3,
        pointHoverRadius: 6,
        spanGaps: true,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index',
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            boxWidth: 12,
            padding: 12,
            font: { size: 12 },
          },
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              const val = context.parsed.y;
              return `${context.dataset.label}: ${val !== null ? val.toFixed(2) : 'N/A'}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            maxTicksLimit: 15,
            font: { size: 11 },
          },
        },
        y: {
          grid: { color: 'rgba(0,0,0,0.06)' },
          ticks: {
            font: { size: 11 },
            callback: (v) => v.toFixed(1),
          },
        },
      },
    },
  });

  canvas._chart = chart;
  return chart;
}

/**
 * 绘制增长率图表（混合柱状图+折线图）
 * @param {HTMLCanvasElement} canvas
 * @param {object} chartData
 * @returns {Chart|null}
 */
export function renderGrowthChart(canvas, chartData) {
  if (!canvas || !chartData || !chartData.labels || !chartData.labels.length) {
    return null;
  }

  const ctx = canvas.getContext('2d');

  if (canvas._chart) {
    canvas._chart.destroy();
  }

  const chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: chartData.labels,
      datasets: chartData.datasets.map(ds => ({
        ...ds,
        type: ds.type || 'bar',
        tension: 0.3,
        pointRadius: 3,
        pointHoverRadius: 5,
        spanGaps: true,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index',
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            boxWidth: 12,
            padding: 12,
            font: { size: 12 },
          },
        },
        tooltip: {
          callbacks: {
            label: function(context) {
              const val = context.parsed.y;
              return `${context.dataset.label}: ${val !== null ? val.toFixed(2) + '%' : 'N/A'}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            maxTicksLimit: 15,
            font: { size: 11 },
          },
        },
        y: {
          grid: { color: 'rgba(0,0,0,0.06)' },
          ticks: {
            font: { size: 11 },
            callback: (v) => v.toFixed(2) + '%',
          },
        },
      },
    },
  });

  canvas._chart = chart;
  return chart;
}
