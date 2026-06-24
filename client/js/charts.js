/**
 * THEIA · 图表渲染模块
 *
 * 基于 Chart.js 绘制 CPI 走势折线图。
 * 复用图表实例更新数据，避免 destroy+recreate 导致的宽度丢失问题。
 */

/* ── 高区分度调色板（12 种视觉差异明显的颜色） ──── */
const COLORS = [
  '#E63946', '#1D3557', '#2A9D8F', '#E76F51',
  '#457B9D', '#6A0572', '#D4A373', '#1A936F',
  '#F4A261', '#264653', '#E5989B', '#5E548E',
];

/* ── 线型样式 ──── */
const DASHES = [
  [],                    // 实线
  [6, 3],                // 虚线
  [2, 3],                // 点线
  [8, 3, 2, 3],          // 虚实线
  [4, 3, 1, 3],          // 点虚线
  [10, 3, 2, 3, 2, 3],   // 长虚实线
];

/* ── 点样式 ──── */
const POINT_STYLES = ['circle', 'triangle', 'rectRot', 'cross', 'star', 'rect'];
const POINT_RADII = [4, 3, 4, 3, 4, 3];

function getDatasetStyle(i) {
  return {
    borderColor: COLORS[i % COLORS.length],
    backgroundColor: COLORS[i % COLORS.length] + '33',
    pointBackgroundColor: COLORS[i % COLORS.length],
    pointBorderColor: '#fff',
    pointBorderWidth: 1.5,
    borderDash: DASHES[i % DASHES.length],
    pointStyle: POINT_STYLES[i % POINT_STYLES.length],
    pointRadius: POINT_RADII[i % POINT_RADII.length],
    pointHoverRadius: 7,
    borderWidth: 2.5,
  };
}

/** 短名称映射（全量，与 app.js 的 CPI_NAME_MAP 和 PPI_NAME_MAP 保持一致） */
const SHORT_LABELS = {
  // ── CPI ──
  '居民消费价格指数 (上年同月=100)': '总 CPI',
  '居民消费价格指数(上年同月=100)': '总 CPI',
  '不包括食品和能源居民消费价格指数 (上年同月=100)': '核心 CPI',
  '不包括食品和能源居民消费价格指数(上年同月=100)': '核心 CPI',
  '食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)': '食品烟酒',
  '食品烟酒及在外餐饮类居民消费价格指数 (上年同月=100)': '食品烟酒',
  '食品烟酒类居民消费价格指数(上年同月=100)': '食品烟酒',
  '食品烟酒类居民消费价格指数 (上年同月=100)': '食品烟酒',
  '居住类居民消费价格指数 (上年同月=100)': '居住',
  '居住类居民消费价格指数(上年同月=100)': '居住',
  '交通通信类居民消费价格指数 (上年同月=100)': '交通通信',
  '交通通信类居民消费价格指数(上年同月=100)': '交通通信',
  '教育文化娱乐类居民消费价格指数 (上年同月=100)': '教育文化',
  '教育文化娱乐类居民消费价格指数(上年同月=100)': '教育文化',
  '医疗保健类居民消费价格指数 (上年同月=100)': '医疗保健',
  '医疗保健类居民消费价格指数(上年同月=100)': '医疗保健',
  '生活用品及服务类居民消费价格指数 (上年同月=100)': '生活用品',
  '生活用品及服务类居民消费价格指数(上年同月=100)': '生活用品',
  '衣着类居民消费价格指数 (上年同月=100)': '衣着',
  '衣着类居民消费价格指数(上年同月=100)': '衣着',
  '其他用品及服务类居民消费价格指数 (上年同月=100)': '其他',
  '其他用品及服务类居民消费价格指数(上年同月=100)': '其他',
  // ── PPI ──
  '工业生产者出厂价格指数 (上年同月=100)': '总 PPI',
  '生产资料工业生产者出厂价格指数 (上年同月=100)': '生产资料PPI',
  '生活资料工业生产者出厂价格指数 (上年同月=100)': '生活资料PPI',
  // ── 货币供应量 ──
  '货币和准货币 (M2) 供应量_同比增长 (%)': 'M2',
  '货币 (M1) 供应量_同比增长 (%)': 'M1',
  '流通中现金 (M0) 供应量_同比增长 (%)': 'M0',
};

/** 折线图 options（共享配置，避免重复创建对象） */
function getLineOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: 'index' },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label(ctx) {
            const val = ctx.parsed.y;
            if (val === null) return `${ctx.dataset.label || ''}: N/A`;
            const sign = val >= 0 ? '+' : '';
            return `${ctx.dataset.label || ''}: ${sign}${val.toFixed(2)}%`;
          },
        },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { maxTicksLimit: 15, font: { size: 11 } } },
      y: {
        grid: { color: 'rgba(0,0,0,0.06)' },
        ticks: { font: { size: 11 }, callback: (v) => (v >= 0 ? '+' : '') + v.toFixed(1) + '%' },
      },
    },
  };
}

/**
 * 构建自定义 HTML 图例
 */
function buildCustomLegend(container, datasets) {
  if (!container) return;
  let html = '';
  for (let i = 0; i < datasets.length; i++) {
    const color = COLORS[i % COLORS.length];
    const dash = DASHES[i % DASHES.length];
    const dashAttr = dash.length > 0 ? `stroke-dasharray="${dash.join(' ')}"` : '';
    const svg = `<svg width="24" height="14" viewBox="0 0 24 14"><line x1="0" y1="7" x2="24" y2="7" stroke="${color}" stroke-width="2.5" ${dashAttr}></line></svg>`;
    const shortLabel = SHORT_LABELS[datasets[i].label] || datasets[i].label || '';
    html += `<div class="custom-legend-item">
      <span class="legend-line">${svg}</span>
      <span class="legend-label">${shortLabel}</span>
      <span class="tooltip-icon legend-tip" data-tip-idx="${i}">ⓘ</span>
    </div>`;
  }
  container.innerHTML = html;
}

/**
 * 复用或创建折线图
 * @param {HTMLCanvasElement} canvas
 * @param {object} chartData - { labels, datasets }
 * @param {string} legendId - 图例容器元素 ID（默认 'chart-legend'）
 * @returns {Chart}
 */
function renderChart(canvas, chartData, legendId) {
  if (!canvas || !chartData || !chartData.labels || !chartData.labels.length) return null;

  const options = getLineOptions();

  const datasets = chartData.datasets.map((ds, i) => ({
    ...ds,
    ...getDatasetStyle(i),
    fill: false,
    tension: 0.3,
    spanGaps: true,
    type: 'line',
    // 缩短标签名
    label: SHORT_LABELS[ds.label] || ds.label,
  }));

  // ── 复用已有图表实例，只更新数据 ──
  if (canvas._chart) {
    const chart = canvas._chart;
    chart.data.labels = chartData.labels;
    chart.data.datasets = datasets;
    chart.update('none');
    // 更新图例
    const legendContainer = document.getElementById(legendId || 'chart-legend');
    if (legendContainer) buildCustomLegend(legendContainer, datasets);
    return chart;
  }

  // ── 首次创建 ──
  const chart = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels: chartData.labels, datasets },
    options,
  });

  canvas._chart = chart;

  const legendContainer = document.getElementById(legendId || 'chart-legend');
  if (legendContainer) buildCustomLegend(legendContainer, datasets);

  return chart;
}

/**
 * 绘制走势图（折线图）
 * @param {HTMLCanvasElement} canvas - 画布元素
 * @param {object} chartData - 图表数据 { labels, datasets }
 * @param {string} legendId - 图例容器 ID（可选，默认 'chart-legend'）
 */
export function renderLineChart(canvas, chartData, legendId) {
  return renderChart(canvas, chartData, legendId);
}
