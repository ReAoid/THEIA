/**
 * THEIA · CPI 数据仪表盘主逻辑
 *
 * 管理全局状态、DOM 渲染、事件绑定。
 */

import {
  fetchOverview,
  fetchIndicators,
  fetchData,
  fetchGrowth,
  fetchSummary,
  fetchChart,
  fetchGroups,
} from '/js/api.js';

import { renderLineChart, renderGrowthChart } from '/js/charts.js';

/* ══════════════════════════════════════════════════════
   全局状态
   ══════════════════════════════════════════════════════ */

const state = {
  indicators: [],          // 指标列表
  groups: [],              // 分组列表
  selectedIndicator: '',   // 当前选中的指标名
  selectedGroup: '',       // 当前选中的分组名
  selectedPeriod: '202406-202605',
  currentPage: 1,
  pageSize: 20,
  allData: [],             // 当前查询的完整数据
  chartType: 'line',       // 'line' | 'growth'
  sortKey: null,
  sortAsc: true,
};

/* ══════════════════════════════════════════════════════
   DOM 引用
   ══════════════════════════════════════════════════════ */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const indicatorSelect = $('#indicator-select');
const groupSelect = $('#group-select');
const periodSelect = $('#period-select');
const refreshBtn = $('#refresh-btn');
const overviewGrid = $('#overview-grid');
const tableBody = $('#table-body');
const tableCount = $('#table-count');
const pagePrev = $('#page-prev');
const pageNext = $('#page-next');
const pageInfo = $('#page-info');
const mainChart = $('#mainChart');
const chartTabs = $$('.chart-tab');

/* ══════════════════════════════════════════════════════
   初始化
   ══════════════════════════════════════════════════════ */

async function init() {
  // 加载指标列表和分组
  await Promise.all([loadIndicators(), loadGroups()]);

  // 绑定事件
  bindEvents();

  // 加载数据
  await refreshAll();
}

/* ══════════════════════════════════════════════════════
   数据加载
   ══════════════════════════════════════════════════════ */

async function loadIndicators() {
  try {
    const res = await fetchIndicators();
    state.indicators = res.data || [];

    // 渲染下拉
    indicatorSelect.innerHTML = '<option value="">全部指标</option>';
    for (const ind of state.indicators) {
      const opt = document.createElement('option');
      opt.value = ind.name;
      opt.textContent = ind.name;
      opt.title = `${ind.name} (${ind.group})`;
      indicatorSelect.appendChild(opt);
    }
  } catch (e) {
    console.error('加载指标列表失败:', e);
    indicatorSelect.innerHTML = '<option value="">加载失败</option>';
  }
}

async function loadGroups() {
  try {
    const res = await fetchGroups();
    state.groups = res.data || [];

    groupSelect.innerHTML = '<option value="">全部分组</option>';
    for (const g of state.groups) {
      const opt = document.createElement('option');
      opt.value = g.name;
      opt.textContent = `${g.name} (${g.indicator_count}项)`;
      groupSelect.appendChild(opt);
    }
  } catch (e) {
    console.error('加载分组列表失败:', e);
  }
}

async function refreshAll() {
  // 显示加载状态
  overviewGrid.innerHTML = '<div class="loading">🔄 加载中...</div>';
  tableBody.innerHTML = '<tr><td colspan="5" class="loading-cell">🔄 加载中...</td></tr>';

  // 构建查询参数
  const params = { period: state.selectedPeriod };
  if (state.selectedIndicator) params.indicator = state.selectedIndicator;
  if (state.selectedGroup) params.group = state.selectedGroup;

  try {
    // 并行请求概览 + 数据 + 图表 + 摘要
    const [overviewRes, dataRes, chartRes, summaryRes] = await Promise.all([
      fetchOverview(params).catch(() => null),
      fetchData(params).catch(() => null),
      fetchChart({ ...params, type: state.chartType }).catch(() => null),
      fetchSummary(params).catch(() => null),
    ]);

    // 渲染概览卡片
    renderOverview(overviewRes);

    // 渲染表格
    state.allData = (dataRes && dataRes.data) || [];
    state.currentPage = 1;
    renderTable();

    // 渲染图表
    renderChart(chartRes);

    // 渲染摘要
    renderSummary(summaryRes);

  } catch (e) {
    console.error('刷新数据失败:', e);
    overviewGrid.innerHTML = `<div class="loading">❌ 加载失败: ${e.message}</div>`;
    tableBody.innerHTML = `<tr><td colspan="5" class="loading-cell">❌ 加载失败: ${e.message}</td></tr>`;
  }
}

/* ══════════════════════════════════════════════════════
   渲染函数
   ══════════════════════════════════════════════════════ */

function renderOverview(res) {
  if (!res || !res.data) {
    overviewGrid.innerHTML = '<div class="loading">📭 无概览数据</div>';
    return;
  }

  const latest = res.data.latest || [];
  const summary = res.data.summary || {};

  let html = `
    <div class="overview-card" style="border-left-color: var(--primary-dark);">
      <div class="indicator-name">总览</div>
      <div class="value" style="font-size:1.2rem;">${summary.total_count || 0} 条</div>
      <div class="meta">${summary.indicator_count || 0} 个指标</div>
      <div class="meta">${summary.date_range || 'N/A'}</div>
    </div>
  `;

  for (const item of latest.slice(0, 12)) {
    const trendIcon = item.trend === 'up' ? '📈' : item.trend === 'down' ? '📉' : '➡️';
    const changeStr = item.latest_change !== null && item.latest_change !== undefined
      ? `(${item.latest_change >= 0 ? '+' : ''}${item.latest_change.toFixed(2)})`
      : '';
    const valColor = item.trend === 'up' ? 'var(--danger)' : item.trend === 'down' ? 'var(--success)' : 'inherit';

    html += `
      <div class="overview-card">
        <div class="indicator-name">${trendIcon} ${escapeHtml(item.indicator)}</div>
        <div class="value" style="color:${valColor}">${item.value !== null && item.value !== undefined ? item.value.toFixed(1) : 'N/A'}</div>
        <div class="meta">
          <span>${item.date || ''}</span>
          <span class="trend-${item.trend || 'stable'}">${changeStr}</span>
        </div>
      </div>
    `;
  }

  overviewGrid.innerHTML = html;
}

function renderTable() {
  const data = state.allData;
  tableCount.textContent = `${data.length} 条`;

  if (!data.length) {
    tableBody.innerHTML = '<tr><td colspan="5" class="loading-cell">📭 暂无数据</td></tr>';
    updatePagination(0);
    return;
  }

  // 排序
  let sorted = [...data];
  if (state.sortKey) {
    sorted.sort((a, b) => {
      const va = a[state.sortKey] ?? '';
      const vb = b[state.sortKey] ?? '';
      if (typeof va === 'number' && typeof vb === 'number') {
        return state.sortAsc ? va - vb : vb - va;
      }
      return state.sortAsc
        ? String(va).localeCompare(String(vb))
        : String(vb).localeCompare(String(va));
    });
  }

  // 分页
  const total = sorted.length;
  const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
  if (state.currentPage > totalPages) state.currentPage = totalPages;
  const start = (state.currentPage - 1) * state.pageSize;
  const pageData = sorted.slice(start, start + state.pageSize);

  let html = '';
  for (const row of pageData) {
    const val = row.value !== null && row.value !== undefined ? row.value.toFixed(2) : 'N/A';
    html += `
      <tr>
        <td>${escapeHtml(row.date || '')}</td>
        <td title="${escapeHtml(row.indicator || '')}">${escapeHtml(truncate(row.indicator || '', 40))}</td>
        <td>${val}</td>
        <td>${escapeHtml(row.unit || '')}</td>
        <td>${escapeHtml(row.region || '')}</td>
      </tr>
    `;
  }

  tableBody.innerHTML = html;
  updatePagination(totalPages);
}

function updatePagination(totalPages) {
  pageInfo.textContent = `第 ${state.currentPage} / ${totalPages} 页`;
  pagePrev.disabled = state.currentPage <= 1;
  pageNext.disabled = state.currentPage >= totalPages;
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

  if (state.chartType === 'growth') {
    renderGrowthChart(mainChart, chartData);
  } else {
    renderLineChart(mainChart, chartData);
  }
}

function renderSummary(res) {
  if (!res || !res.data || !res.data.details) {
    document.getElementById('summary-grid').innerHTML = '<div class="loading">📭 无摘要数据</div>';
    return;
  }

  const details = res.data.details;
  let html = '';

  for (const [name, info] of Object.entries(details)) {
    const trendIcon = info.trend === 'up' ? '📈' : info.trend === 'down' ? '📉' : '➡️';
    html += `
      <div class="summary-item">
        <div class="si-name">${trendIcon} ${escapeHtml(name)}</div>
        <div class="si-grid">
          <span class="label">最新</span>
          <span class="value">${info.latest ? info.latest.value : 'N/A'} (${info.latest ? info.latest.date : ''})</span>
          <span class="label">均值</span>
          <span class="value">${info.mean !== undefined ? info.mean.toFixed(2) : 'N/A'}</span>
          <span class="label">最高</span>
          <span class="value">${info.max ? info.max.value : 'N/A'} (${info.max ? info.max.date : ''})</span>
          <span class="label">最低</span>
          <span class="value">${info.min ? info.min.value : 'N/A'} (${info.min ? info.min.date : ''})</span>
          <span class="label">波动</span>
          <span class="value">${info.volatility !== undefined ? info.volatility.toFixed(2) : 'N/A'}</span>
          <span class="label">标准差</span>
          <span class="value">${info.std !== undefined ? info.std.toFixed(2) : 'N/A'}</span>
        </div>
      </div>
    `;
  }

  document.getElementById('summary-grid').innerHTML = html;
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

/* ══════════════════════════════════════════════════════
   事件绑定
   ══════════════════════════════════════════════════════ */

function bindEvents() {
  // 指标选择
  indicatorSelect.addEventListener('change', () => {
    state.selectedIndicator = indicatorSelect.value;
    state.selectedGroup = '';       // 分组/指标互斥
    groupSelect.value = '';
    refreshAll();
  });

  // 分组选择
  groupSelect.addEventListener('change', () => {
    state.selectedGroup = groupSelect.value;
    state.selectedIndicator = '';   // 分组/指标互斥
    indicatorSelect.value = '';
    refreshAll();
  });

  // 时间段选择
  periodSelect.addEventListener('change', () => {
    state.selectedPeriod = periodSelect.value;
    refreshAll();
  });

  // 刷新按钮
  refreshBtn.addEventListener('click', refreshAll);

  // 分页
  pagePrev.addEventListener('click', () => {
    if (state.currentPage > 1) {
      state.currentPage--;
      renderTable();
    }
  });

  pageNext.addEventListener('click', () => {
    const totalPages = Math.max(1, Math.ceil(state.allData.length / state.pageSize));
    if (state.currentPage < totalPages) {
      state.currentPage++;
      renderTable();
    }
  });

  // 表头排序
  document.querySelectorAll('#data-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) {
        state.sortAsc = !state.sortAsc;
      } else {
        state.sortKey = key;
        state.sortAsc = true;
      }

      // 更新排序图标
      document.querySelectorAll('#data-table th[data-sort]').forEach(h => {
        h.classList.remove('sort-asc', 'sort-desc');
      });
      th.classList.add(state.sortAsc ? 'sort-asc' : 'sort-desc');

      state.currentPage = 1;
      renderTable();
    });
  });

  // 图表标签切换
  chartTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      chartTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.chartType = tab.dataset.type;
      // 重新加载图表
      loadChartOnly();
    });
  });
}

async function loadChartOnly() {
  const params = { period: state.selectedPeriod, type: state.chartType };
  if (state.selectedIndicator) params.indicator = state.selectedIndicator;
  if (state.selectedGroup) params.group = state.selectedGroup;

  try {
    const res = await fetchChart(params);
    renderChart(res);
  } catch (e) {
    console.error('加载图表失败:', e);
  }
}

/* ══════════════════════════════════════════════════════
   启动
   ══════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', init);
