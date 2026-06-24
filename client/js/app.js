/**
 * THEIA · 经济数据仪表盘 - 主逻辑
 *
 * 管理仪表盘布局、页面切换、CPI 数据渲染。
 */

import {
  fetchOverview,
  fetchIndicators,
  fetchData,
  fetchChart,
  fetchGroups,
  fetchPpiOverview,
  fetchPpiIndicators,
  fetchPpiData,
  fetchPpiChart,
  fetchPpiGroups,
  fetchMsOverview,
  fetchMsIndicators,
  fetchMsData,
  fetchMsChart,
  fetchMsGroups,
  fetchMsYoy,
} from '/js/api.js';

import { renderLineChart } from '/js/charts.js';

/* ══════════════════════════════════════════════════════
   全局状态
   ══════════════════════════════════════════════════════ */

const state = {
  indicators: [],
  groups: [],
  selectedIndicator: '',
  selectedGroup: '',
  selectedPeriod: '202406-202605',
  allData: [],
  chartType: 'line',
  currentSection: 'cpi',
  // 图表多选指标（默认全部）
  chartSelectedIndicators: [],
  chartIndicatorAllSelected: true,
};

/* ══════════════════════════════════════════════════════
   PPI 状态
   ══════════════════════════════════════════════════════ */

const ppiState = {
  indicators: [],
  groups: [],
  selectedIndicator: '',
  selectedGroup: '',
  selectedPeriod: '202506-202606',
  allData: [],
  chartSelectedIndicators: [],
  chartIndicatorAllSelected: true,
};

/* ══════════════════════════════════════════════════════
   货币供应量状态
   ══════════════════════════════════════════════════════ */

const msState = {
  indicators: [],
  groups: [],
  selectedPeriod: '200001-202606',
  allData: [],
};

/* ══════════════════════════════════════════════════════
   DOM 引用
   ══════════════════════════════════════════════════════ */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const refreshBtn = $('#refresh-btn');
const overviewGrid = $('#overview-grid');

const mainChart = $('#mainChart');
const chartTabs = $$('.chart-tab');
const sidebarToggle = $('#sidebar-toggle');
const sidebar = $('#sidebar');
const toolbarTitle = $('#toolbar-title');
const lastUpdate = $('#last-update');
const navLinks = $$('.nav-link');

// 时间段自定义输入（起始+结束） + 预设按钮
const periodStart = $('#period-start');
const periodEnd = $('#period-end');
const periodPresetBtns = $$('.period-preset-btn');
const chartTabsDash = $('#section-dashboard .chart-tab');

// 图表指标多选
const chartIndicatorBtn = $('#chart-indicator-btn');
const chartIndicatorDropdown = $('#chart-indicator-dropdown');
const chartIndicatorList = $('#chart-indicator-list');
const chartCheckall = $('#chart-checkall');

// ── PPI DOM 引用 ─────────────────────────────────────
const ppiOverviewGrid = $('#ppi-overview-grid');
const ppiChart = $('#ppi-chart');
const ppiPeriodStart = $('#ppi-period-start');
const ppiPeriodEnd = $('#ppi-period-end');
const ppiPeriodPresetBtns = $$('.ppi-period-preset-btn');
const ppiChartIndicatorBtn = $('#ppi-chart-indicator-btn');
const ppiChartIndicatorDropdown = $('#ppi-chart-indicator-dropdown');
const ppiChartIndicatorList = $('#ppi-chart-indicator-list');
const ppiChartCheckall = $('#ppi-chart-checkall');

// ── 货币供应量 DOM 引用 ──────────────────────────────
const msChart = $('#ms-chart');
const msPeriodStart = $('#ms-period-start');
const msPeriodEnd = $('#ms-period-end');
const msPeriodPresetBtns = $$('.ms-period-preset-btn');
const msYoyTbody = $('#ms-yoy-tbody');
const msAbsoluteGrid = $('#ms-absolute-grid');
const msKpiTotal = $('#ms-kpi-total');
const msKpiIndicators = $('#ms-kpi-indicators');
const msKpiLatestM2 = $('#ms-kpi-latest-m2');
const msM2Change = $('#ms-m2-change');
const msKpiTimespan = $('#ms-kpi-timespan');

/* ══════════════════════════════════════════════════════
   初始化
   ══════════════════════════════════════════════════════ */

async function init() {
  // 加载指标列表
  await loadIndicators();
  await loadPpiIndicators();
  await loadMsIndicators();

  // 绑定事件
  bindEvents();

  // 初始化默认时间段
  initDefaultPeriod();
  initPpiDefaultPeriod();
  initMsDefaultPeriod();

  // 切换到 CPI 页面并加载数据
  switchSection('cpi');
  await refreshAll();
}

/* ══════════════════════════════════════════════════════
   数据加载
   ══════════════════════════════════════════════════════ */

async function loadIndicators() {
  try {
    const res = await fetchIndicators();
    state.indicators = res.data || [];
    // 初始化图表指标多选列表
    buildChartIndicatorList();
  } catch (e) {
    console.error('加载指标列表失败:', e);
  }
}

/* ── PPI 数据加载 ───────────────────────────────── */

async function loadPpiIndicators() {
  try {
    const res = await fetchPpiIndicators();
    ppiState.indicators = res.data || [];
    ppiState.groups = res.groups || [];
    buildPpiChartIndicatorList();
  } catch (e) {
    console.error('加载 PPI 指标列表失败:', e);
  }
}

async function refreshPpi() {
  ppiOverviewGrid.innerHTML = '<div class="loading">🔄 加载中...</div>';

  const currentPeriod = getCurrentPpiPeriod();
  const params = { period: currentPeriod };

  // 图表参数
  const chartParams = { period: currentPeriod };
  if (ppiState.chartSelectedIndicators.length > 0) {
    chartParams.indicator = ppiState.chartSelectedIndicators.join(',');
  }

  try {
    const [overviewRes, dataRes, chartRes] = await Promise.all([
      fetchPpiOverview(params).catch(() => null),
      fetchPpiData(params).catch(() => null),
      fetchPpiChart(chartParams).catch(() => null),
    ]);

    renderPpiOverview(overviewRes);
    renderPpiKpiCards(overviewRes);

    ppiState.allData = (dataRes && dataRes.data) || [];

    renderPpiChart(chartRes);

    lastUpdate.textContent = `已更新 ${formatTime(new Date())}`;

  } catch (e) {
    console.error('刷新 PPI 数据失败:', e);
    ppiOverviewGrid.innerHTML = `<div class="loading">❌ 加载失败: ${e.message}</div>`;
  }
}

async function refreshAll() {
  // 显示加载状态
  overviewGrid.innerHTML = '<div class="loading">🔄 加载中...</div>';

  const currentPeriod = getCurrentPeriod();
  const params = { period: currentPeriod };
  if (state.selectedIndicator) params.indicator = state.selectedIndicator;
  if (state.selectedGroup) params.group = state.selectedGroup;

  // 图表参数：优先使用图表多选指标
  const chartParams = { period: currentPeriod };
  if (state.chartSelectedIndicators.length > 0) {
    chartParams.indicator = state.chartSelectedIndicators.join(',');
  } else if (state.selectedIndicator) {
    chartParams.indicator = state.selectedIndicator;
  }
  if (state.selectedGroup) chartParams.group = state.selectedGroup;

  try {
    const [overviewRes, dataRes, chartRes] = await Promise.all([
      fetchOverview(params).catch(() => null),
      fetchData(params).catch(() => null),
      fetchChart(chartParams).catch(() => null),
    ]);

    renderOverview(overviewRes);
    renderKpiCards(overviewRes);

    state.allData = (dataRes && dataRes.data) || [];

    renderChart(chartRes);

    // 更新时间戳
    lastUpdate.textContent = `已更新 ${formatTime(new Date())}`;

  } catch (e) {
    console.error('刷新数据失败:', e);
    overviewGrid.innerHTML = `<div class="loading">❌ 加载失败: ${e.message}</div>`;
  }
}

/* ══════════════════════════════════════════════════════
   渲染函数
   ══════════════════════════════════════════════════════ */

function renderKpiCards(res) {
  if (!res || !res.data) return;

  const latest = res.data.latest || [];
  // 兼容两种字段名：API 返回的 summary.count / summary.indicators
  // 以及顶层 data.total_count / data.indicator_count
  const summary = res.data.summary || {};
  const totalCount = summary.count ?? summary.total_count ?? res.data.total_count ?? 0;
  const indicatorCount = summary.indicators ?? summary.indicator_count ?? res.data.indicator_count ?? 0;

  // 数据总量
  const totalEl = $('#kpi-total');
  if (totalEl) totalEl.textContent = totalCount.toLocaleString();

  // 指标数量
  const indEl = $('#kpi-indicators');
  if (indEl) indEl.textContent = indicatorCount + ' 项';

  // 时间跨度
  const spanEl = $('#kpi-timespan');
  if (spanEl) spanEl.textContent = summary.date_range || '--';

  // 最新 CPI — 找第一个指标（显示为增速值）
  const cpiEl = $('#kpi-latest-cpi');
  const cpiChangeEl = $('#kpi-cpi-change');
  if (cpiEl && latest.length > 0) {
    const first = latest[0];
    const growthVal = cpiToGrowth(first.value);
    cpiEl.textContent = growthVal !== null
      ? (growthVal >= 0 ? '+' : '') + growthVal.toFixed(1)
      : '--';
    if (cpiChangeEl) {
      if (first.latest_change !== null && first.latest_change !== undefined) {
        const sign = first.latest_change >= 0 ? '+' : '';
        const cls = first.latest_change >= 0 ? 'positive' : 'negative';
        cpiChangeEl.textContent = `↑ ${sign}${first.latest_change.toFixed(2)} 较上期`;
        cpiChangeEl.className = `kpi-change ${cls}`;
      } else {
        cpiChangeEl.textContent = '暂无环比数据';
      }
    }
  }
}

function renderOverview(res) {
  if (!res || !res.data) {
    overviewGrid.innerHTML = '<div class="loading">📭 无概览数据</div>';
    return;
  }

  const latest = res.data.latest || [];
  const summary = res.data.summary || {};
  // 兼容 summary 中的键名
  const totalCount = summary.count ?? summary.total_count ?? 0;
  const indicatorCount = summary.indicators ?? summary.indicator_count ?? 0;

  // 指标顺序说明 + 悬浮 Tooltip（总CPI → 核心CPI → 八大标准分项）
  let orderHtml = '<div class="order-legend">';
  const orderNames = [
    { name: '总 CPI', label: '总 CPI' },
    { name: '核心 CPI', label: '核心 CPI' },
    { name: '居住类', label: '居住' },
    { name: '食品烟酒及在外餐饮类', label: '食品烟酒' },
    { name: '交通通信类', label: '交通通信' },
    { name: '教育文化娱乐类', label: '教育文化' },
    { name: '医疗保健类', label: '医疗保健' },
    { name: '生活用品及服务类', label: '生活用品' },
    { name: '衣着类', label: '衣着' },
    { name: '其他用品及服务类', label: '其他' },
  ];
  orderNames.forEach((item, idx) => {
    const color = getIndicatorColor(idx);
    const tip = INDICATOR_TOOLTIPS[item.name];
    if (tip) {
      orderHtml += `
        <div class="order-tooltip-item">
          <span class="order-dot" style="background:${color}"></span>
          <span class="order-label">${item.label}</span>
          <span class="tooltip-icon" data-tip-idx="${idx}">ⓘ</span>
        </div>
      `;
    }
  });
  orderHtml += '</div>';

  let html = orderHtml;
  html += `
    <div class="overview-card" style="border-left-color: var(--primary-dark);">
      <div class="indicator-name">总览</div>
      <div class="value" style="font-size:1.1rem;">${totalCount} 条</div>
      <div class="meta">${indicatorCount} 个指标 · ${summary.date_range || 'N/A'}</div>
    </div>
  `;

  // 合并同名指标（如食品烟酒跨周期两个名称），按标准顺序排列
  const mergedLatest = mergeLatest(latest);
  const sortedLatest = sortByIndicatorOrder(mergedLatest, 'indicator');
  for (const item of sortedLatest) {
    const trendIcon = item.trend === 'up' ? '📈' : item.trend === 'down' ? '📉' : '➡️';
    const changeStr = item.latest_change !== null && item.latest_change !== undefined
      ? `(${item.latest_change >= 0 ? '+' : ''}${item.latest_change.toFixed(2)})`
      : '';
    const valColor = item.trend === 'up' ? 'var(--danger)' : item.trend === 'down' ? 'var(--success)' : 'inherit';

    const displayVal = cpiToGrowth(item.value);
    const valStr = displayVal !== null
      ? (displayVal >= 0 ? '+' : '') + displayVal.toFixed(1) + '%'
      : 'N/A';
    html += `
      <div class="overview-card">
        <div class="indicator-name">${trendIcon} ${escapeHtml(item.indicator)}</div>
        <div class="value" style="color:${valColor}">${valStr}</div>
        <div class="meta">
          <span>${item.date || ''}</span>
          <span class="trend-${item.trend || 'stable'}">${changeStr}</span>
        </div>
      </div>
    `;
  }

  overviewGrid.innerHTML = html;
}



function renderChart(res) {
  const chartData = res && res.data;
  if (!chartData || !chartData.labels || !chartData.labels.length) {
    mainChart.style.display = 'none';
    document.getElementById('chart-empty').style.display = 'block';
    return;
  }

  mainChart.style.display = 'block';
  document.getElementById('chart-empty').style.display = 'none';

  // 合并同名指标数据集（如食品烟酒跨周期两个名称）
  const mergedDatasets = mergeDatasets(chartData.datasets || []);

  // 按指标顺序排序
  const sortedDatasets = sortByIndicatorOrder(mergedDatasets, 'label');

  // 将官方同比指数（上年同月=100）转换为增速值（指数 - 100）
  const transformedData = {
    labels: chartData.labels,
    datasets: sortedDatasets.map(ds => ({
      ...ds,
      data: ds.data.map(v => v !== null && v !== undefined ? v - 100 : null),
    })),
  };

  renderLineChart(mainChart, transformedData);
}

/* ══════════════════════════════════════════════════════
   PPI 渲染函数
   ══════════════════════════════════════════════════════ */

function renderPpiKpiCards(res) {
  if (!res || !res.data) return;

  const latest = res.data.latest || [];
  const summary = res.data.summary || {};
  const totalCount = summary.count ?? res.data.total_count ?? 0;
  const indicatorCount = summary.indicators ?? res.data.indicator_count ?? 0;

  const totalEl = $('#ppi-kpi-total');
  if (totalEl) totalEl.textContent = totalCount.toLocaleString();

  const indEl = $('#ppi-kpi-indicators');
  if (indEl) indEl.textContent = indicatorCount + ' 项';

  const spanEl = $('#ppi-kpi-timespan');
  if (spanEl) spanEl.textContent = summary.date_range || '--';

  // 最新 PPI
  const ppiEl = $('#ppi-kpi-latest-ppi');
  const ppiChangeEl = $('#ppi-ppi-change');
  if (ppiEl && latest.length > 0) {
    const first = latest[0];
    const growthVal = cpiToGrowth(first.value);
    ppiEl.textContent = growthVal !== null
      ? (growthVal >= 0 ? '+' : '') + growthVal.toFixed(1)
      : '--';
    if (ppiChangeEl) {
      if (first.latest_change !== null && first.latest_change !== undefined) {
        const sign = first.latest_change >= 0 ? '+' : '';
        const cls = first.latest_change >= 0 ? 'positive' : 'negative';
        ppiChangeEl.textContent = `↑ ${sign}${first.latest_change.toFixed(2)} 较上期`;
        ppiChangeEl.className = `kpi-change ${cls}`;
      } else {
        ppiChangeEl.textContent = '暂无环比数据';
      }
    }
  }
}

function renderPpiOverview(res) {
  if (!res || !res.data) {
    ppiOverviewGrid.innerHTML = '<div class="loading">📭 无概览数据</div>';
    return;
  }

  const latest = res.data.latest || [];
  const summary = res.data.summary || {};
  const totalCount = summary.count ?? summary.total_count ?? 0;
  const indicatorCount = summary.indicators ?? summary.indicator_count ?? 0;

  // 指标顺序说明
  const orderNames = [
    { name: '总 PPI', label: '总 PPI', tip: PPI_INDICATOR_TOOLTIPS['总 PPI'] },
    { name: '生产资料PPI', label: '生产资料', tip: PPI_INDICATOR_TOOLTIPS['生产资料PPI'] },
    { name: '生活资料PPI', label: '生活资料', tip: PPI_INDICATOR_TOOLTIPS['生活资料PPI'] },
  ];

  let html = '<div class="order-legend">';
  orderNames.forEach((item, idx) => {
    const color = getPpiColor(idx);
    html += `
      <div class="order-tooltip-item">
        <span class="order-dot" style="background:${color}"></span>
        <span class="order-label">${item.label}</span>
        <span class="tooltip-icon" data-ppi-tip-idx="${idx}">ⓘ</span>
      </div>
    `;
  });
  html += '</div>';

  html += `
    <div class="overview-card" style="border-left-color: #e63946;">
      <div class="indicator-name">总览</div>
      <div class="value" style="font-size:1.1rem;">${totalCount} 条</div>
      <div class="meta">${indicatorCount} 个指标 · ${summary.date_range || 'N/A'}</div>
    </div>
  `;

  const sortedLatest = sortByPpiOrder(latest, 'indicator');
  for (const item of sortedLatest) {
    const shortName = ppiNormName(item.indicator);
    const trendIcon = item.trend === 'up' ? '📈' : item.trend === 'down' ? '📉' : '➡️';
    const changeStr = item.latest_change !== null && item.latest_change !== undefined
      ? `(${item.latest_change >= 0 ? '+' : ''}${item.latest_change.toFixed(2)})`
      : '';
    const valColor = item.trend === 'up' ? 'var(--danger)' : item.trend === 'down' ? 'var(--success)' : 'inherit';

    const displayVal = cpiToGrowth(item.value);
    const valStr = displayVal !== null
      ? (displayVal >= 0 ? '+' : '') + displayVal.toFixed(1) + '%'
      : 'N/A';
    html += `
      <div class="overview-card">
        <div class="indicator-name">${trendIcon} ${escapeHtml(shortName)}</div>
        <div class="value" style="color:${valColor}">${valStr}</div>
        <div class="meta">
          <span>${item.date || ''}</span>
          <span class="trend-${item.trend || 'stable'}">${changeStr}</span>
        </div>
      </div>
    `;
  }

  ppiOverviewGrid.innerHTML = html;
}

function renderPpiChart(res) {
  const chartData = res && res.data;
  if (!chartData || !chartData.labels || !chartData.labels.length) {
    ppiChart.style.display = 'none';
    document.getElementById('ppi-chart-empty').style.display = 'block';
    return;
  }

  ppiChart.style.display = 'block';
  document.getElementById('ppi-chart-empty').style.display = 'none';

  const shortDatasets = (chartData.datasets || []).map(ds => ({
    ...ds,
    label: ppiNormName(ds.label),
  }));

  const sortedDatasets = sortByPpiOrder(shortDatasets, 'label');

  // 同比指数 → 增速
  const transformedData = {
    labels: chartData.labels,
    datasets: sortedDatasets.map(ds => ({
      ...ds,
      data: ds.data.map(v => v !== null && v !== undefined ? v - 100 : null),
    })),
  };

  renderLineChart(ppiChart, transformedData, 'ppi-chart-legend');
}

/* ══════════════════════════════════════════════════════
   货币供应量渲染函数
   ══════════════════════════════════════════════════════ */

async function loadMsIndicators() {
  try {
    const res = await fetchMsIndicators();
    msState.indicators = res.data || [];
    msState.groups = res.groups || [];
  } catch (e) {
    console.error('加载货币供应量指标列表失败:', e);
  }
}

async function refreshMs() {
  msAbsoluteGrid.innerHTML = '<div class="loading">🔄 加载中...</div>';

  const currentPeriod = getCurrentMsPeriod();
  const params = { period: currentPeriod };

  try {
    // 并行加载概览 + 图表 + 绝对值数据
    const [overviewRes, chartRes] = await Promise.all([
      fetchMsOverview(params).catch(() => null),
      fetchMsChart({ ...params, indicator: '同比增长' }).catch(() => null),
    ]);

    // 渲染 KPI
    renderMsKpiCards(overviewRes);

    // 渲染图表（同比增长走势）
    renderMsChart(chartRes);

    // 渲染绝对值（只取最新一个月）
    await renderMsAbsoluteGrid();

    lastUpdate.textContent = `已更新 ${formatTime(new Date())}`;

  } catch (e) {
    console.error('刷新货币供应量数据失败:', e);
    msAbsoluteGrid.innerHTML = `<div class="loading">❌ 加载失败: ${e.message}</div>`;
  }
}

function renderMsKpiCards(res) {
  if (!res || !res.data) return;

  const latest = res.data.latest || [];
  const summary = res.data.summary || {};
  const totalCount = summary.count ?? res.data.total_count ?? 0;
  const indicatorCount = summary.indicators ?? res.data.indicator_count ?? 0;

  if (msKpiTotal) msKpiTotal.textContent = totalCount.toLocaleString();
  if (msKpiIndicators) msKpiIndicators.textContent = indicatorCount + ' 项';
  if (msKpiTimespan) msKpiTimespan.textContent = summary.date_range || '--';

  // 最新 M2 同比
  if (msKpiLatestM2 && latest.length > 0) {
    // 找 M2 同比增长
    const m2yoy = latest.find(l => l.indicator && l.indicator.includes('M2') && l.indicator.includes('同比'));
    if (m2yoy) {
      const val = m2yoy.value !== null && m2yoy.value !== undefined ? m2yoy.value : null;
      msKpiLatestM2.textContent = val !== null ? val.toFixed(1) + '%' : '--';
      if (msM2Change) {
        msM2Change.textContent = `最新 ${m2yoy.date || ''}`;
      }
    } else {
      msKpiLatestM2.textContent = '--';
    }
  }
}

function renderMsChart(res) {
  const chartData = res && res.data;
  if (!chartData || !chartData.labels || !chartData.labels.length) {
    if (msChart) msChart.style.display = 'none';
    const emptyEl = document.getElementById('ms-chart-empty');
    if (emptyEl) emptyEl.style.display = 'block';
    return;
  }

  if (msChart) msChart.style.display = 'block';
  const emptyEl = document.getElementById('ms-chart-empty');
  if (emptyEl) emptyEl.style.display = 'none';

  // 数据处理：已经是增速值，直接使用
  // 构建短名映射 + tooltip 数据属性
  const msShortNames = {
    '货币和准货币 (M2) 供应量_同比增长 (%)': 'M2',
    '货币 (M1) 供应量_同比增长 (%)': 'M1',
    '流通中现金 (M0) 供应量_同比增长 (%)': 'M0',
  };

  const transformedData = {
    labels: chartData.labels,
    datasets: (chartData.datasets || []).map((ds, i) => ({
      ...ds,
      label: msShortNames[ds.label] || ds.label.replace(/_/g, ' '),
      _msKey: msShortNames[ds.label] || '',  // 用于 tooltip 查找
    })),
  };

  renderLineChart(msChart, transformedData, 'ms-chart-legend');

  // 替换图例中的 tooltip 数据属性为 ms-tip
  const legendEl = document.getElementById('ms-chart-legend');
  if (legendEl) {
    const tips = legendEl.querySelectorAll('.legend-tip');
    tips.forEach(tip => {
      const idx = parseInt(tip.dataset.tipIdx, 10);
      if (!isNaN(idx) && idx < transformedData.datasets.length) {
        const msKey = transformedData.datasets[idx]._msKey;
        if (msKey) {
          delete tip.dataset.tipIdx;
          tip.dataset.msTip = msKey;
        }
      }
    });
  }
}

async function renderMsAbsoluteGrid() {
  try {
    // 只拉最新一个月的期末值数据
    const latestMonth = getLatestMsMonth();
    const period = `${latestMonth}`;
    const params = { period, group: '期末值' };
    const dataRes = await fetchMsData(params);
    const data = (dataRes && dataRes.data) || [];

    if (!data.length) {
      msAbsoluteGrid.innerHTML = '<div class="loading">📭 暂无数据</div>';
      return;
    }

    // 按 M2、M1、M0 排序
    const orderMap = { 'M2': 0, 'M1': 1, 'M0': 2 };
    const sorted = [...data].sort((a, b) => {
      const aKey = Object.keys(orderMap).find(k => a.indicator.includes(k)) || '';
      const bKey = Object.keys(orderMap).find(k => b.indicator.includes(k)) || '';
      return (orderMap[aKey] ?? 99) - (orderMap[bKey] ?? 99);
    });

    const latestDate = sorted[0]?.date || '';

    let html = `<div class="overview-card" style="border-left-color: var(--primary-dark);">
      <div class="indicator-name">${latestDate}</div>
      <div class="value" style="font-size:1.1rem;">${sorted.length} 项</div>
      <div class="meta">货币供应量期末值</div>
    </div>`;

    for (const item of sorted) {
      const val = item.value !== null && item.value !== undefined
        ? Number(item.value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        : 'N/A';
      const shortName = item.indicator.replace(/\s*\(.*?\)\s*/g, '').trim();
      html += `
        <div class="overview-card">
          <div class="indicator-name">💰 ${escapeHtml(shortName)}</div>
          <div class="value" style="font-size:1rem;">${val}</div>
          <div class="meta">${item.unit || '亿元'}</div>
        </div>
      `;
    }

    msAbsoluteGrid.innerHTML = html;
  } catch (e) {
    console.error('加载货币供应量绝对值失败:', e);
    msAbsoluteGrid.innerHTML = `<div class="loading">❌ 加载失败: ${e.message}</div>`;
  }
}

/* ── 货币供应量时间段辅助 ──────────────────────── */

function getCurrentMsPeriod() {
  const s = msPeriodStart ? msPeriodStart.value.trim() : '';
  const e = msPeriodEnd ? msPeriodEnd.value.trim() : '';
  if (s && e) return `${s}-${e}`;
  return '200001-202606';
}

function initMsDefaultPeriod() {
  const endYM = getLatestMsMonth();
  if (msPeriodStart) msPeriodStart.value = '200001';
  if (msPeriodEnd) msPeriodEnd.value = endYM;
  msState.selectedPeriod = `200001-${endYM}`;
}

function getLatestMsMonth() {
  const now = new Date();
  return `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}`;
}

/* ══════════════════════════════════════════════════════
   页面切换
   ══════════════════════════════════════════════════════ */

function switchSection(sectionId) {
  state.currentSection = sectionId;

  // 切换 nav 高亮
  navLinks.forEach(link => {
    link.classList.toggle('active', link.dataset.section === sectionId);
  });

  // 切换页面内容
  document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
  const target = document.getElementById(`section-${sectionId}`);
  if (target) target.classList.add('active');

  // 更新工具栏标题
  const nameMap = {
    dashboard: '仪表盘总览',
    cpi: 'CPI 消费价格指数',
    ppi: 'PPI 生产价格指数',
    'money-supply': '货币供应量',
    analysis: '深度分析',
    settings: '数据设置',
  };
  toolbarTitle.textContent = nameMap[sectionId] || sectionId;

  // 切换时自动加载对应数据
  if (sectionId === 'ppi' && ppiState.indicators.length > 0) {
    initPpiDefaultPeriod();
    refreshPpi();
  }

  if (sectionId === 'money-supply') {
    initMsDefaultPeriod();
    refreshMs();
  }

  // 在小屏幕上关闭侧边栏
  if (window.innerWidth <= 768) {
    sidebar.classList.remove('open');
  }
}

/* ══════════════════════════════════════════════════════
   工具函数
   ══════════════════════════════════════════════════════ */

function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function truncate(text, maxLen) {
  if (!text) return '';
  return text.length > maxLen ? text.slice(0, maxLen) + '…' : text;
}

function formatTime(date) {
  const h = String(date.getHours()).padStart(2, '0');
  const m = String(date.getMinutes()).padStart(2, '0');
  return `${h}:${m}`;
}

/* ── 数值转换：官方同比指数 → 增速展示 ──────────── */

/**
 * 将官方同比指数（上年同月=100）转换为增速值（指数 - 100）。
 * 例如：101.5 → 1.5，99.8 → -0.2
 */
function cpiToGrowth(val) {
  if (val === null || val === undefined) return null;
  return val - 100;
}

/* ── CPI 指标名称归一化 ────────────────────────────
 *
 * 国家统计局在不同周期（2021-2025、2026-2030）对同一经济指标
 * 使用了不同的 UUID 和名称，此映射将全量已知名称统一为短名。
 */

/** 全量名称 → 短名映射 */
const CPI_NAME_MAP = {
  // 总 CPI
  '居民消费价格指数 (上年同月=100)': '总 CPI',
  '居民消费价格指数(上年同月=100)': '总 CPI',
  // 核心 CPI
  '不包括食品和能源居民消费价格指数 (上年同月=100)': '核心 CPI',
  '不包括食品和能源居民消费价格指数(上年同月=100)': '核心 CPI',
  // 食品烟酒（跨周期名称不同）
  '食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)': '食品烟酒',
  '食品烟酒及在外餐饮类居民消费价格指数 (上年同月=100)': '食品烟酒',
  '食品烟酒类居民消费价格指数(上年同月=100)': '食品烟酒',
  '食品烟酒类居民消费价格指数 (上年同月=100)': '食品烟酒',
  // 居住
  '居住类居民消费价格指数 (上年同月=100)': '居住',
  '居住类居民消费价格指数(上年同月=100)': '居住',
  // 交通通信
  '交通通信类居民消费价格指数 (上年同月=100)': '交通通信',
  '交通通信类居民消费价格指数(上年同月=100)': '交通通信',
  // 教育文化娱乐
  '教育文化娱乐类居民消费价格指数 (上年同月=100)': '教育文化',
  '教育文化娱乐类居民消费价格指数(上年同月=100)': '教育文化',
  // 医疗保健
  '医疗保健类居民消费价格指数 (上年同月=100)': '医疗保健',
  '医疗保健类居民消费价格指数(上年同月=100)': '医疗保健',
  // 生活用品及服务
  '生活用品及服务类居民消费价格指数 (上年同月=100)': '生活用品',
  '生活用品及服务类居民消费价格指数(上年同月=100)': '生活用品',
  // 衣着
  '衣着类居民消费价格指数 (上年同月=100)': '衣着',
  '衣着类居民消费价格指数(上年同月=100)': '衣着',
  // 其他用品及服务
  '其他用品及服务类居民消费价格指数 (上年同月=100)': '其他',
  '其他用品及服务类居民消费价格指数(上年同月=100)': '其他',
};

/* ── PPI 指标名称归一化 ──────────────────────────── */

/** 全量名称 → 短名映射 */
const PPI_NAME_MAP = {
  '工业生产者出厂价格指数 (上年同月=100)': '总 PPI',
  '生产资料工业生产者出厂价格指数 (上年同月=100)': '生产资料PPI',
  '生活资料工业生产者出厂价格指数 (上年同月=100)': '生活资料PPI',
};

/**
 * 将 PPI 指标全名归一化为短名。
 */
function ppiNormName(fullName) {
  return PPI_NAME_MAP[fullName] || fullName;
}

/**
 * 将 CPI 指标全名归一化为短名。
 * 如果找不到映射，返回原始名称。
 */
function normName(fullName) {
  return CPI_NAME_MAP[fullName] || fullName;
}

/**
 * 对数据集（数组）按归一化名称合并：
 * 同名的 data 数组按索引取第一个非空值合并。
 */
function mergeDatasets(datasets) {
  const groups = {};
  for (const ds of datasets) {
    const shortName = normName(ds.label);
    if (!groups[shortName]) {
      groups[shortName] = { ...ds, label: shortName, data: [...ds.data] };
    } else {
      // 合并 data：优先用非空值
      const target = groups[shortName];
      for (let i = 0; i < ds.data.length; i++) {
        if (target.data[i] === null || target.data[i] === undefined) {
          target.data[i] = ds.data[i];
        }
      }
    }
  }
  return Object.values(groups);
}

/**
 * 对 latest/overview 数组按归一化名称去重合并，
 * 同名保留日期最新的那条。
 */
function mergeLatest(items) {
  const groups = {};
  for (const item of items) {
    const shortName = normName(item.indicator || item.name || '');
    if (!groups[shortName] || item.date > groups[shortName].date) {
      groups[shortName] = { ...item, indicator: shortName };
    }
  }
  return Object.values(groups);
}



/* ── 指标 Tooltip 说明 ──────────────────────────── */

const INDICATOR_TOOLTIPS = {
  '总 CPI': {
    meaning: '八大类全部商品、服务加权汇总的整体物价指数。',
    importance: '市场、政策最基础通胀标尺，包含食品、能源短期波动，用来直观感知全社会整体物价涨跌。',
  },
  '核心 CPI': {
    meaning: '剔除波动剧烈的食品烟酒、汽油柴油，只留下稳定商品与服务。',
    importance: '央行判断中长期真实内需的核心指标，滤掉猪肉、油价短期干扰，反映可持续的内生通胀，直接左右货币宽松 / 收紧决策。',
  },
  '居住类': {
    meaning: '房租、水电燃气、物业费、装修住房相关开销。',
    importance: '权重最高，核心 CPI 核心分项，代表长期真实内需，直接影响货币政策判断。',
  },
  '食品烟酒及在外餐饮类': {
    meaning: '肉菜粮油、烟酒、餐馆外卖。',
    importance: 'CPI 短期波动主要来源，民生重点调控项，核心 CPI 直接剔除这一项。',
  },
  '交通通信类': {
    meaning: '汽油、汽车、机票、话费手机。',
    importance: '国际油价输入通胀的主要渠道，用来区分能源涨价和真实出行需求。',
  },
  '教育文化娱乐类': {
    meaning: '培训学费、旅游酒店、电影景区。',
    importance: '代表线下可选服务消费，用来判断消费复苏强弱。',
  },
  '医疗保健类': {
    meaning: '药品、诊疗、体检护理。',
    importance: '常年小幅平稳上涨，波动极小，对整体通胀影响微弱。',
  },
  '生活用品及服务类': {
    meaning: '家电、日化、家政维修。',
    importance: '跟随上游工业品价格滞后变动，仅辅助看成本传导。',
  },
  '衣着类': {
    meaning: '衣服鞋帽、洗护缝纫。',
    importance: '权重低、换季波动大，长期无趋势，宏观分析基本不用看。',
  },
  '其他用品及服务类': {
    meaning: '美妆首饰、婚庆美发等杂项消费。',
    importance: '品类分散，几乎不影响整体 CPI，常规分析可忽略。',
  },
};

/* ── PPI 指标 Tooltip 说明 ──────────────────────── */

const PPI_INDICATOR_TOOLTIPS = {
  '总 PPI': {
    meaning: '全部工业品出厂价格综合指数，大家口中标准 PPI。',
    importance: '核心工业通胀指标，和 CPI 搭配判断工业冷热、通缩 / 通胀，是政策与市场分析的基准。',
  },
  '生产资料PPI': {
    meaning: '原油、煤炭、钢铁、化工等上游原料、中间工业品，占 PPI 权重 80%。',
    importance: '主导总 PPI 涨跌，跟踪国际大宗商品、基建地产周期，涨跌直接影响工厂原材料成本与利润。',
  },
  '生活资料PPI': {
    meaning: '家电、加工食品、服装等卖给居民的工业消费品，占 PPI 权重 20%。',
    importance: '判断上游成本能否传导到终端消费，走势可提前预判 CPI 商品端物价变化。',
  },
};

/* ── 货币供应量指标 Tooltip 说明 ──────────────── */

const MS_TOOLTIPS = {
  'M0': {
    meaning: '市面上所有纸币、硬币（手里的现金）。',
    represents: '线下现金消费。',
    importance: '参考价值最低，波动基本是节假日导致，不判断经济大势。',
  },
  'M1': {
    meaning: 'M0 + 企业活期、个人活期（随时能花的钱）。',
    represents: '真实经济活力、企业生意好坏。',
    importance: 'M1上涨=企业敢接单、敢投资、经济回暖；M1低迷=企业观望、市场冷清。',
  },
  'M2': {
    meaning: 'M1 + 定期存款、储蓄、理财等所有沉淀资金（全社会所有钱）。',
    represents: '市场货币总量、货币政策松紧。',
    importance: 'M2涨=放水、宽松；M2跌=收紧、缺钱。是判断宏观流动性的核心指标。',
  },
};

/* ── 指标排序（总PPI → 两大分项） ──────────────── */

/** PPI 全名顺序 */
const PPI_INDICATOR_ORDER = [
  '工业生产者出厂价格指数 (上年同月=100)',
  '生产资料工业生产者出厂价格指数 (上年同月=100)',
  '生活资料工业生产者出厂价格指数 (上年同月=100)',
];

/** PPI 短名顺序 */
const PPI_INDICATOR_ORDER_SHORT = [
  '总 PPI',
  '生产资料PPI',
  '生活资料PPI',
];

/* ── 指标排序（总CPI → 核心CPI → 八大标准分项） ──── */

/** 全名顺序（2026-2030 周期） */
const INDICATOR_ORDER = [
  '居民消费价格指数 (上年同月=100)',
  '不包括食品和能源居民消费价格指数 (上年同月=100)',
  '居住类居民消费价格指数 (上年同月=100)',
  '食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)',
  '交通通信类居民消费价格指数 (上年同月=100)',
  '教育文化娱乐类居民消费价格指数 (上年同月=100)',
  '医疗保健类居民消费价格指数 (上年同月=100)',
  '生活用品及服务类居民消费价格指数 (上年同月=100)',
  '衣着类居民消费价格指数 (上年同月=100)',
  '其他用品及服务类居民消费价格指数 (上年同月=100)',
];

/** 全名顺序（2021-2025 周期） */
const INDICATOR_ORDER_2021 = [
  '居民消费价格指数(上年同月=100)',
  '不包括食品和能源居民消费价格指数 (上年同月=100)',
  '居住类居民消费价格指数(上年同月=100)',
  '食品烟酒类居民消费价格指数(上年同月=100)',
  '交通通信类居民消费价格指数(上年同月=100)',
  '教育文化娱乐类居民消费价格指数(上年同月=100)',
  '医疗保健类居民消费价格指数(上年同月=100)',
  '生活用品及服务类居民消费价格指数(上年同月=100)',
  '衣着类居民消费价格指数(上年同月=100)',
  '其他用品及服务类居民消费价格指数 (上年同月=100)',
];

/**
 * 短名顺序（与 CPI_NAME_MAP 归一化后的结果对应）
 *
 * 经过 mergeDatasets/mergeLatest/mergeSummaryDetails 等函数
 * 归一化后，指标名称变为短名（如 '总 CPI'、'核心 CPI'、'居住'）。
 * 此数组用于在这些场景下保持正确的排序。
 */
const INDICATOR_ORDER_SHORT = [
  '总 CPI',
  '核心 CPI',
  '居住',
  '食品烟酒',
  '交通通信',
  '教育文化',
  '医疗保健',
  '生活用品',
  '衣着',
  '其他',
];

/**
 * 构建统一的指标排序映射表（合并全名 + 短名）
 * @returns {Map<string, number>} 名称 → 排序索引的映射
 */
function buildIndicatorOrderMap() {
  const map = new Map();
  let idx = 0;

  // 按顺序依次添加：总CPI → 核心CPI → 八大标准分项
  for (let i = 0; i < INDICATOR_ORDER_SHORT.length; i++) {
    const shortName = INDICATOR_ORDER_SHORT[i];
    const fullName = INDICATOR_ORDER[i];
    const fullName2021 = INDICATOR_ORDER_2021[i];

    if (!map.has(shortName)) map.set(shortName, idx);
    if (fullName && !map.has(fullName)) map.set(fullName, idx);
    if (fullName2021 && !map.has(fullName2021)) map.set(fullName2021, idx);

    idx++;
  }

  return map;
}

/** 全局排序映射（构建一次） */
const _ORDER_MAP = buildIndicatorOrderMap();

/**
 * 按预设顺序对 indicator 数组排序
 * @param {string[]} names - 指标名称数组
 * @param {string[]} items - 要排序的完整对象数组，每个对象有 .indicator 或 .name 属性
 * @param {string} keyField - 对象中的名称字段，默认 'indicator'
 * @returns {Array} 排序后的新数组
 */
function sortByIndicatorOrder(items, keyField = 'indicator') {
  function getOrder(item) {
    const name = item[keyField] || '';
    if (_ORDER_MAP.has(name)) return _ORDER_MAP.get(name);

    // 降级匹配：去掉括号内容后匹配
    const stripped = name.replace(/\(.*?\)/g, '').trim();
    if (_ORDER_MAP.has(stripped)) return _ORDER_MAP.get(stripped);

    // 再降级：遍历 map 中每个 key 去掉括号后比较
    for (const [key, rank] of _ORDER_MAP) {
      if (key.replace(/\(.*?\)/g, '').trim() === stripped) return rank;
    }

    // 再降级：用 CPI_NAME_MAP 反查短名后匹配
    for (const [full, short] of Object.entries(CPI_NAME_MAP)) {
      if (name === full) {
        const shortRank = _ORDER_MAP.get(short);
        if (shortRank !== undefined) return shortRank;
        break;
      }
    }

    return 999;
  }
  return [...items].sort((a, b) => getOrder(a) - getOrder(b));
}

/* ══════════════════════════════════════════════════════
   事件绑定
   ══════════════════════════════════════════════════════ */

function bindEvents() {
  // 侧边栏导航
  navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      switchSection(link.dataset.section);
    });
  });

  // 侧边栏切换（移动端）
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
  }

  // 点击侧边栏外部关闭
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 &&
        sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) &&
        !sidebarToggle.contains(e.target)) {
      sidebar.classList.remove('open');
    }
  });

  // 刷新（根据当前页面类型）
  refreshBtn.addEventListener('click', () => {
    if (state.currentSection === 'ppi') {
      refreshPpi();
    } else if (state.currentSection === 'money-supply') {
      refreshMs();
    } else {
      refreshAll();
    }
  });

  // 时间段输入（起始/结束，回车或失焦触发）
  [periodStart, periodEnd].forEach(input => {
    if (!input) return;
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        applyPeriodFromInput();
      }
    });
    input.addEventListener('blur', () => {
      applyPeriodFromInput();
    });
  });

  // 预设时间段按钮
  periodPresetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const months = parseInt(btn.dataset.months, 10);
      const isAll = btn.dataset.all === '1';
      if (isAll) {
        // 全部数据（CPI 最早数据从 2021 年开始）
        if (periodStart) periodStart.value = '202101';
        if (periodEnd) periodEnd.value = getLatestMonth();
      } else if (!isNaN(months)) {
        const endYM = getLatestMonth();
        const startYM = subtractMonths(endYM, months - 1);
        if (periodStart) periodStart.value = startYM;
        if (periodEnd) periodEnd.value = endYM;
      }
      periodPresetBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      refreshAll();
    });
  });

  // 图表标签（仅保留折线图，移除增长率切换按钮）
  document.querySelectorAll('.chart-tab[data-type="growth"]').forEach(el => el.remove());

  // 图表指标下拉按钮
  if (chartIndicatorBtn) {
    chartIndicatorBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      chartIndicatorDropdown.classList.toggle('open');
    });
  }

  // 点击外部关闭下拉
  document.addEventListener('click', (e) => {
    if (chartIndicatorDropdown &&
        chartIndicatorDropdown.classList.contains('open') &&
        !chartIndicatorDropdown.contains(e.target) &&
        e.target !== chartIndicatorBtn) {
      chartIndicatorDropdown.classList.remove('open');
    }
  });

  // 全选
  if (chartCheckall) {
    chartCheckall.addEventListener('change', () => {
      const checked = chartCheckall.checked;
      chartIndicatorList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.checked = checked;
      });
      syncChartSelectedIndicators();
      loadChartOnly();
    });
  }

  // 图表指标列表事件（委托）
  if (chartIndicatorList) {
    chartIndicatorList.addEventListener('change', (e) => {
      if (e.target.type === 'checkbox' && e.target.id !== 'chart-checkall') {
        syncChartSelectedIndicators();
        loadChartOnly();
      }
    });
  }

  // ═══ PPI 事件绑定 ═══════════════════════════════

  // PPI 时间段输入
  [ppiPeriodStart, ppiPeriodEnd].forEach(input => {
    if (!input) return;
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        refreshPpi();
      }
    });
    input.addEventListener('blur', () => {
      refreshPpi();
    });
  });

  // PPI 预设时间段按钮
  ppiPeriodPresetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const months = parseInt(btn.dataset.months, 10);
      const isAll = btn.dataset.all === '1';
      if (isAll) {
        if (ppiPeriodStart) ppiPeriodStart.value = '200001';
        if (ppiPeriodEnd) ppiPeriodEnd.value = getLatestPpiMonth();
      } else if (!isNaN(months)) {
        const endYM = getLatestPpiMonth();
        const startYM = subtractMonths(endYM, months - 1);
        if (ppiPeriodStart) ppiPeriodStart.value = startYM;
        if (ppiPeriodEnd) ppiPeriodEnd.value = endYM;
      }
      ppiPeriodPresetBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      refreshPpi();
    });
  });

  // PPI 图表指标下拉按钮
  if (ppiChartIndicatorBtn) {
    ppiChartIndicatorBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      ppiChartIndicatorDropdown.classList.toggle('open');
    });
  }

  // 点击外部关闭 PPI 下拉
  document.addEventListener('click', (e) => {
    if (ppiChartIndicatorDropdown &&
        ppiChartIndicatorDropdown.classList.contains('open') &&
        !ppiChartIndicatorDropdown.contains(e.target) &&
        e.target !== ppiChartIndicatorBtn) {
      ppiChartIndicatorDropdown.classList.remove('open');
    }
  });

  // PPI 全选
  if (ppiChartCheckall) {
    ppiChartCheckall.addEventListener('change', () => {
      const checked = ppiChartCheckall.checked;
      ppiChartIndicatorList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.checked = checked;
      });
      syncPpiChartSelectedIndicators();
      refreshPpi();
    });
  }

  // PPI 图表指标列表事件（委托）
  if (ppiChartIndicatorList) {
    ppiChartIndicatorList.addEventListener('change', (e) => {
      if (e.target.type === 'checkbox' && e.target.id !== 'ppi-chart-checkall') {
        syncPpiChartSelectedIndicators();
        refreshPpi();
      }
    });
  }

  // ═══ 货币供应量事件绑定 ══════════════════════════

  // MS 时间段输入
  [msPeriodStart, msPeriodEnd].forEach(input => {
    if (!input) return;
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        refreshMs();
      }
    });
    input.addEventListener('blur', () => {
      refreshMs();
    });
  });

  // MS 预设时间段按钮
  msPeriodPresetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const months = parseInt(btn.dataset.months, 10);
      const isAll = btn.dataset.all === '1';
      if (isAll) {
        // 全部数据
        if (msPeriodStart) msPeriodStart.value = '200001';
        if (msPeriodEnd) msPeriodEnd.value = getLatestMsMonth();
      } else if (!isNaN(months)) {
        const endYM = getLatestMsMonth();
        const startYM = subtractMonths(endYM, months - 1);
        if (msPeriodStart) msPeriodStart.value = startYM;
        if (msPeriodEnd) msPeriodEnd.value = endYM;
      }
      msPeriodPresetBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      refreshMs();
    });
  });

  // ═══ PPI 悬浮 Tooltip ═══
  initPpiFloatingTooltip();

  // ═══ 悬浮 Tooltip（委托，不受 overflow 影响） ═══
  initFloatingTooltip();
}

/**
 * 构建图表指标多选列表（按分组归类）
 *
 * 分组结构：
 *   总 CPI      → 居民消费价格指数
 *   核心 CPI     → 不包括食品和能源居民消费价格指数
 *   八大标准分项  → 食品烟酒、衣着、居住、生活用品及服务、
 *                  交通通信、教育文化娱乐、医疗保健、其他用品及服务
 */
function buildChartIndicatorList() {
  if (!chartIndicatorList) return;

  const indicators = state.indicators;
  if (!indicators.length) {
    chartIndicatorList.innerHTML = '<div class="dropdown-loading">暂无指标</div>';
    return;
  }

  // 只保留三个目标分组下的指标
  const targetGroups = ['总CPI', '核心CPI', '八大标准分项'];
  const filtered = indicators.filter(ind => targetGroups.includes(ind.group));

  if (!filtered.length) {
    // 兜底：如果后端没返回 group 信息，改用名称关键词匹配
    // 同时包含新旧两个周期的指标名称
    const keywords = [
      '居民消费价格指数 (上年同月=100)',
      '居民消费价格指数(上年同月=100)',
      '不包括食品和能源居民消费价格指数 (上年同月=100)',
      '食品烟酒及在外餐饮类',
      '食品烟酒类',
      '衣着类',
      '居住类',
      '生活用品及服务类',
      '交通通信类',
      '教育文化娱乐类',
      '医疗保健类',
      '其他用品及服务类',
    ];
    for (const kw of keywords) {
      const match = indicators.find(ind => ind.name.includes(kw));
      if (match && !filtered.includes(match)) {
        filtered.push(match);
      }
    }
  }

  // 去重（同名只保留第一个）
  const seen = new Set();
  const unique = filtered.filter(ind => {
    // 取简名去重（去掉 "(上年同月=100)" 部分）
    const key = ind.name.replace(/\(.*?\)/g, '').trim();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  // 指标名称顺序映射（用于组内排序）
  const orderMap = new Map();
  const allOrders = [...INDICATOR_ORDER, ...INDICATOR_ORDER_2021];
  allOrders.forEach((name, i) => { if (!orderMap.has(name)) orderMap.set(name, i); });
  function getNameOrder(ind) {
    if (orderMap.has(ind.name)) return orderMap.get(ind.name);
    const stripped = ind.name.replace(/\(.*?\)/g, '').trim();
    for (const [key, idx] of orderMap) {
      if (key.replace(/\(.*?\)/g, '').trim() === stripped) return idx;
    }
    return 999;
  }

  // 按分组顺序排列，组内按指标顺序
  const groupOrder = { '总CPI': 0, '核心CPI': 1, '八大标准分项': 2 };
  unique.sort((a, b) => {
    const gDiff = (groupOrder[a.group] ?? 99) - (groupOrder[b.group] ?? 99);
    if (gDiff !== 0) return gDiff;
    return getNameOrder(a) - getNameOrder(b);
  });

  // 默认只选中总 CPI 和核心 CPI（同时包含新旧周期名称）
  const defaultNames = [
    '居民消费价格指数 (上年同月=100)',
    '居民消费价格指数(上年同月=100)',
    '不包括食品和能源居民消费价格指数 (上年同月=100)',
    '不包括食品和能源居民消费价格指数(上年同月=100)',
  ];
  state.chartSelectedIndicators = unique
    .filter(ind => defaultNames.some(d => ind.name === d))
    .map(ind => ind.name);
  state.chartIndicatorAllSelected = false;

  // 分组构建 HTML
  const groupLabels = {
    '总CPI': '总 CPI',
    '核心CPI': '核心 CPI',
    '八大标准分项': '八大标准分项',
  };

  const groupMap = {};
  for (const ind of unique) {
    const g = ind.group || '其他';
    if (!groupMap[g]) groupMap[g] = [];
    groupMap[g].push(ind);
  }

  let colorIndex = 0;
  let html = '';
  for (const gName of ['总CPI', '核心CPI', '八大标准分项']) {
    const items = groupMap[gName];
    if (!items || !items.length) continue;

    // 组内按指标顺序排序
    items.sort((a, b) => getNameOrder(a) - getNameOrder(b));

    html += `<div class="dropdown-group-label">${groupLabels[gName] || gName}</div>`;

    for (const ind of items) {
      const checked = state.chartSelectedIndicators.includes(ind.name) ? 'checked' : '';
      const disabled = !ind.has_data ? 'disabled' : '';
      const note = !ind.has_data ? ' (无数据)' : '';
      html += `
        <label class="dropdown-item ${disabled}">
          <input type="checkbox" value="${escapeHtml(ind.name)}" ${checked} ${disabled}>
          <span class="item-color-dot" style="background:${getIndicatorColor(colorIndex)}"></span>
          <span class="item-name">${escapeHtml(ind.name)}${note}</span>
        </label>
      `;
      colorIndex++;
    }
  }

  chartIndicatorList.innerHTML = html;

  if (chartCheckall) {
    chartCheckall.checked = state.chartIndicatorAllSelected;
  }
}

/**
 * 同步选中状态到 state
 */
function syncChartSelectedIndicators() {
  const checked = [];
  chartIndicatorList.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
    checked.push(cb.value);
  });
  state.chartSelectedIndicators = checked;
  // 计算总可选指标数（仅含目标分组下的）
  const totalCheckboxes = chartIndicatorList.querySelectorAll('input[type="checkbox"]').length;
  state.chartIndicatorAllSelected =
    checked.length === totalCheckboxes;
  if (chartCheckall) {
    chartCheckall.checked = state.chartIndicatorAllSelected;
  }
}

/* ══════════════════════════════════════════════════════
   PPI 图表指标多选
   ══════════════════════════════════════════════════════ */

/**
 * 同步 PPI 选中状态
 */
function syncPpiChartSelectedIndicators() {
  const checked = [];
  ppiChartIndicatorList.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
    checked.push(cb.value);
  });
  ppiState.chartSelectedIndicators = checked;
  const totalCheckboxes = ppiChartIndicatorList.querySelectorAll('input[type="checkbox"]').length;
  ppiState.chartIndicatorAllSelected = checked.length === totalCheckboxes;
  if (ppiChartCheckall) {
    ppiChartCheckall.checked = ppiState.chartIndicatorAllSelected;
  }
}

/**
 * 构建 PPI 图表指标多选列表
 */
function buildPpiChartIndicatorList() {
  if (!ppiChartIndicatorList) return;

  const indicators = ppiState.indicators;
  if (!indicators.length) {
    ppiChartIndicatorList.innerHTML = '<div class="dropdown-loading">暂无指标</div>';
    return;
  }

  // 默认只选中总 PPI
  ppiState.chartSelectedIndicators = indicators
    .filter(ind => ind.group === '总PPI')
    .map(ind => ind.name);
  ppiState.chartIndicatorAllSelected = false;

  const groupLabels = { '总PPI': '总 PPI', '两大分项': '两大分项' };

  const groupMap = {};
  for (const ind of indicators) {
    const g = ind.group || '其他';
    if (!groupMap[g]) groupMap[g] = [];
    groupMap[g].push(ind);
  }

  let colorIndex = 0;
  let html = '';
  for (const gName of ['总PPI', '两大分项']) {
    const items = groupMap[gName];
    if (!items || !items.length) continue;

    html += `<div class="dropdown-group-label">${groupLabels[gName] || gName}</div>`;

    for (const ind of items) {
      const checked = ppiState.chartSelectedIndicators.includes(ind.name) ? 'checked' : '';
      const disabled = !ind.has_data ? 'disabled' : '';
      const note = !ind.has_data ? ' (无数据)' : '';
      html += `
        <label class="dropdown-item ${disabled}">
          <input type="checkbox" value="${escapeHtml(ind.name)}" ${checked} ${disabled}>
          <span class="item-color-dot" style="background:${getPpiColor(colorIndex)}"></span>
          <span class="item-name">${escapeHtml(ind.name)}${note}</span>
        </label>
      `;
      colorIndex++;
    }
  }

  ppiChartIndicatorList.innerHTML = html;

  if (ppiChartCheckall) {
    ppiChartCheckall.checked = ppiState.chartIndicatorAllSelected;
  }
}

/* ══════════════════════════════════════════════════════
   PPI 时间段辅助
   ══════════════════════════════════════════════════════ */

/**
 * 获取 PPI 最新数据月份
 */
function getLatestPpiMonth() {
  if (ppiState.allData && ppiState.allData.length > 0) {
    const dates = ppiState.allData.map(d => d.date).filter(Boolean).sort();
    if (dates.length > 0) {
      return dates[dates.length - 1].replace('-', '');
    }
  }
  const now = new Date();
  return `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}`;
}

/**
 * 货币供应量悬浮 Tooltip 内容
 */
function getMsTooltipContent(key) {
  const tip = MS_TOOLTIPS[key];
  if (!tip) return '';
  return `
    <div class="tooltip-line"><b>含义：</b>${escapeHtml(tip.meaning)}</div>
    <div class="tooltip-line"><b>代表什么：</b>${escapeHtml(tip.represents)}</div>
    <div class="tooltip-line"><b>重要性：</b>${escapeHtml(tip.importance)}</div>
  `;
}

/**
 * PPI 悬浮 Tooltip（body 层级）
 */
function getPpiTooltipContent(idx) {
  const tooltipData = [
    { name: '总 PPI', tip: PPI_INDICATOR_TOOLTIPS['总 PPI'] },
    { name: '生产资料PPI', tip: PPI_INDICATOR_TOOLTIPS['生产资料PPI'] },
    { name: '生活资料PPI', tip: PPI_INDICATOR_TOOLTIPS['生活资料PPI'] },
  ];
  const data = tooltipData[idx];
  if (!data || !data.tip) return '';
  return `
    <div class="tooltip-line"><b>含义：</b>${escapeHtml(data.tip.meaning)}</div>
    <div class="tooltip-line"><b>重要性：</b>${escapeHtml(data.tip.importance)}</div>
  `;
}

function initPpiFloatingTooltip() {
  const tooltipEl = document.getElementById('global-tooltip');
  if (!tooltipEl) return;

  let activeIcon = null;

  document.addEventListener('mouseenter', (e) => {
    const target = e.target;
    const icon = target instanceof Element ? target.closest('[data-ppi-tip-idx]') : null;
    if (!icon || icon === activeIcon) return;
    activeIcon = icon;

    const idx = parseInt(icon.dataset.ppiTipIdx, 10);
    if (isNaN(idx)) return;
    const content = getPpiTooltipContent(idx);
    if (!content) return;

    tooltipEl.querySelector('.global-tooltip-body').innerHTML = content;

    const rect = icon.getBoundingClientRect();
    const tipW = 300;
    let left = rect.left + rect.width / 2 - tipW / 2;
    if (left < 10) left = 10;
    if (left + tipW > window.innerWidth - 10) left = window.innerWidth - tipW - 10;

    tooltipEl.style.left = left + 'px';
    tooltipEl.style.top = (rect.top - 10) + 'px';
    tooltipEl.style.display = 'block';
  }, true);

  document.addEventListener('mouseleave', (e) => {
    const target = e.target;
    const icon = target instanceof Element ? target.closest('[data-ppi-tip-idx]') : null;
    if (icon && icon === activeIcon) {
      activeIcon = null;
      tooltipEl.style.display = 'none';
    }
  }, true);

  tooltipEl.addEventListener('mouseenter', () => { tooltipEl.style.display = 'block'; });
  tooltipEl.addEventListener('mouseleave', () => { activeIcon = null; tooltipEl.style.display = 'none'; });
}

/**
 * 图表指标颜色（与 charts.js 的 COLORS 调色板同步）
 */
function getIndicatorColor(index) {
  const colors = [
    '#E63946', '#1D3557', '#2A9D8F', '#E76F51',
    '#457B9D', '#6A0572', '#D4A373', '#1A936F',
    '#F4A261', '#264653', '#E5989B', '#5E548E',
  ];
  return colors[index % colors.length];
}

function getPpiColor(index) {
  const colors = ['#E63946', '#1D3557', '#2A9D8F'];
  return colors[index % colors.length];
}

/**
 * PPI 指标排序映射表
 */
function buildPpiOrderMap() {
  const map = new Map();
  PPI_INDICATOR_ORDER_SHORT.forEach((shortName, i) => {
    const fullName = PPI_INDICATOR_ORDER[i];
    if (!map.has(shortName)) map.set(shortName, i);
    if (fullName && !map.has(fullName)) map.set(fullName, i);
  });
  return map;
}

const _PPI_ORDER_MAP = buildPpiOrderMap();

/**
 * 按 PPI 预设顺序排序
 */
function sortByPpiOrder(items, keyField = 'indicator') {
  function getOrder(item) {
    const name = item[keyField] || '';
    if (_PPI_ORDER_MAP.has(name)) return _PPI_ORDER_MAP.get(name);
    const stripped = name.replace(/\(.*?\)/g, '').trim();
    for (const [key, rank] of _PPI_ORDER_MAP) {
      if (key.replace(/\(.*?\)/g, '').trim() === stripped) return rank;
    }
    return 999;
  }
  return [...items].sort((a, b) => getOrder(a) - getOrder(b));
}

async function loadChartOnly() {
  const params = { period: getCurrentPeriod() };

  // 使用图表多选的指标（如果未选任何指标，传空则后端返回全部）
  if (state.chartSelectedIndicators.length > 0) {
    params.indicator = state.chartSelectedIndicators.join(',');
  }

  try {
    const res = await fetchChart(params);
    renderChart(res);
  } catch (e) {
    console.error('加载图表失败:', e);
  }
}

/* ── 时间段辅助函数 ───────────────────────────── */

/**
 * 获取当前输入框中的时间段
 */
function getCurrentPeriod() {
  const s = periodStart ? periodStart.value.trim() : '';
  const e = periodEnd ? periodEnd.value.trim() : '';
  if (s && e) return `${s}-${e}`;
  return '202406-202605';
}

/**
 * 获取 PPI 输入框中的时间段
 */
function getCurrentPpiPeriod() {
  const s = ppiPeriodStart ? ppiPeriodStart.value.trim() : '';
  const e = ppiPeriodEnd ? ppiPeriodEnd.value.trim() : '';
  if (s && e) return `${s}-${e}`;
  return '202506-202606';
}

/**
 * 从输入框获取时间段并刷新
 */
function applyPeriodFromInput() {
  const s = periodStart ? periodStart.value.trim() : '';
  const e = periodEnd ? periodEnd.value.trim() : '';
  if (/^\d{6}$/.test(s) && /^\d{6}$/.test(e)) {
    refreshAll();
  } else {
    // 标记错误的输入框
    if (periodStart && !/^\d{6}$/.test(s)) {
      periodStart.classList.add('input-error');
      setTimeout(() => periodStart.classList.remove('input-error'), 1500);
    }
    if (periodEnd && !/^\d{6}$/.test(e)) {
      periodEnd.classList.add('input-error');
      setTimeout(() => periodEnd.classList.remove('input-error'), 1500);
    }
  }
}

/**
 * 获取最新数据月份（从缓存或当前时间推导）
 */
function getLatestMonth() {
  // 优先从缓存数据中获取最新月份
  if (state.allData && state.allData.length > 0) {
    const dates = state.allData.map(d => d.date).filter(Boolean).sort();
    if (dates.length > 0) {
      return dates[dates.length - 1].replace('-', '');
    }
  }
  // 兜底：当前月份
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  return `${y}${String(m).padStart(2, '0')}`;
}

/**
 * 将 YYYYMM 减去 N 个月
 */
function subtractMonths(yyyymm, n) {
  let y = parseInt(yyyymm.substring(0, 4), 10);
  let m = parseInt(yyyymm.substring(4, 6), 10);
  m -= n;
  while (m <= 0) {
    y -= 1;
    m += 12;
  }
  return `${y}${String(m).padStart(2, '0')}`;
}

/**
 * 加载完成后初始化默认时间段（近12个月）
 */
/* ── 悬浮 Tooltip（body 层级，不受 overflow 遮挡） ── */

/** 指标 tooltip HTML 内容（按索引映射） */
function getTooltipContent(idx) {
  const tooltipData = [
    { name: '总 CPI', tip: INDICATOR_TOOLTIPS['总 CPI'] },
    { name: '核心 CPI', tip: INDICATOR_TOOLTIPS['核心 CPI'] },
    { name: '居住类', tip: INDICATOR_TOOLTIPS['居住类'] },
    { name: '食品烟酒及在外餐饮类', tip: INDICATOR_TOOLTIPS['食品烟酒及在外餐饮类'] },
    { name: '交通通信类', tip: INDICATOR_TOOLTIPS['交通通信类'] },
    { name: '教育文化娱乐类', tip: INDICATOR_TOOLTIPS['教育文化娱乐类'] },
    { name: '医疗保健类', tip: INDICATOR_TOOLTIPS['医疗保健类'] },
    { name: '生活用品及服务类', tip: INDICATOR_TOOLTIPS['生活用品及服务类'] },
    { name: '衣着类', tip: INDICATOR_TOOLTIPS['衣着类'] },
    { name: '其他用品及服务类', tip: INDICATOR_TOOLTIPS['其他用品及服务类'] },
  ];
  const data = tooltipData[idx];
  if (!data || !data.tip) return '';
  return `
    <div class="tooltip-line"><b>含义：</b>${escapeHtml(data.tip.meaning)}</div>
    <div class="tooltip-line"><b>重要性：</b>${escapeHtml(data.tip.importance)}</div>
  `;
}

function initFloatingTooltip() {
  const tooltipEl = document.getElementById('global-tooltip');
  if (!tooltipEl) return;

  let activeIcon = null;

  // ⓘ 上 mouseenter → 显示
  document.addEventListener('mouseenter', (e) => {
    const target = e.target;
    const icon = target instanceof Element ? target.closest('.tooltip-icon') : null;
    if (!icon || icon === activeIcon) return;
    activeIcon = icon;

    // 判断 tooltip 类型
    const tipIdx = icon.dataset.tipIdx;       // CPI chart
    const msTip = icon.dataset.msTip;          // MS chart

    let content = '';
    if (tipIdx !== undefined) {
      const idx = parseInt(tipIdx, 10);
      if (!isNaN(idx)) content = getTooltipContent(idx);
    } else if (msTip !== undefined) {
      content = getMsTooltipContent(msTip);
    }

    if (!content) return;

    tooltipEl.querySelector('.global-tooltip-body').innerHTML = content;

    const rect = icon.getBoundingClientRect();
    const tipW = 300;
    let left = rect.left + rect.width / 2 - tipW / 2;
    if (left < 10) left = 10;
    if (left + tipW > window.innerWidth - 10) left = window.innerWidth - tipW - 10;

    tooltipEl.style.left = left + 'px';
    tooltipEl.style.top = (rect.top - 10) + 'px';
    tooltipEl.style.display = 'block';
  }, true);

  // ⓘ 上 mouseleave → 隐藏
  document.addEventListener('mouseleave', (e) => {
    const target = e.target;
    const icon = target instanceof Element ? target.closest('.tooltip-icon') : null;
    if (icon && icon === activeIcon) {
      activeIcon = null;
      tooltipEl.style.display = 'none';
    }
  }, true);

  // tooltip 自身 mouseenter → 保持显示
  tooltipEl.addEventListener('mouseenter', () => {
    tooltipEl.style.display = 'block';
  });

  // tooltip 自身 mouseleave → 隐藏
  tooltipEl.addEventListener('mouseleave', () => {
    activeIcon = null;
    tooltipEl.style.display = 'none';
  });
}

function initDefaultPeriod() {
  const endYM = getLatestMonth();
  const startYM = subtractMonths(endYM, 11);
  if (periodStart) periodStart.value = startYM;
  if (periodEnd) periodEnd.value = endYM;
  state.selectedPeriod = `${startYM}-${endYM}`;
}

function initPpiDefaultPeriod() {
  const endYM = getLatestPpiMonth();
  const startYM = subtractMonths(endYM, 11);
  if (ppiPeriodStart) ppiPeriodStart.value = startYM;
  if (ppiPeriodEnd) ppiPeriodEnd.value = endYM;
  ppiState.selectedPeriod = `${startYM}-${endYM}`;
}

/* 暴露 switchSection 给全局，用于 HTML 中的 onclick */
window.switchSection = switchSection;

/* ══════════════════════════════════════════════════════
   启动
   ══════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', init);
