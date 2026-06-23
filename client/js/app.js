/**
 * THEIA · 经济数据仪表盘 - 主逻辑
 *
 * 管理仪表盘布局、页面切换、CPI 数据渲染。
 */

import {
  fetchOverview,
  fetchIndicators,
  fetchData,
  fetchSummary,
  fetchChart,
  fetchGroups,
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
  currentPage: 1,
  pageSize: 20,
  allData: [],
  chartType: 'line',
  sortKey: null,
  sortAsc: true,
  currentSection: 'cpi',
  // 图表多选指标（默认全部）
  chartSelectedIndicators: [],        // 选中的 indicator name 列表
  chartIndicatorAllSelected: true,     // 是否全选
};

/* ══════════════════════════════════════════════════════
   DOM 引用
   ══════════════════════════════════════════════════════ */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const refreshBtn = $('#refresh-btn');
const overviewGrid = $('#overview-grid');
const tableBody = $('#table-body');
const tableCount = $('#table-count');
const pagePrev = $('#page-prev');
const pageNext = $('#page-next');
const pageInfo = $('#page-info');
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

/* ══════════════════════════════════════════════════════
   初始化
   ══════════════════════════════════════════════════════ */

async function init() {
  // 加载指标列表
  await loadIndicators();

  // 绑定事件
  bindEvents();

  // 切换到 CPI 页面并加载数据
  switchSection('cpi');
  await refreshAll();

  // 加载完成后计算并设置默认时间段
  initDefaultPeriod();


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

async function refreshAll() {
  // 显示加载状态
  overviewGrid.innerHTML = '<div class="loading">🔄 加载中...</div>';
  tableBody.innerHTML = '<tr><td colspan="5" class="loading-cell">🔄 加载中...</td></tr>';

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
    const [overviewRes, dataRes, chartRes, summaryRes] = await Promise.all([
      fetchOverview(params).catch(() => null),
      fetchData(params).catch(() => null),
      fetchChart(chartParams).catch(() => null),
      fetchSummary(params).catch(() => null),
    ]);

    renderOverview(overviewRes);
    renderKpiCards(overviewRes);

    state.allData = (dataRes && dataRes.data) || [];
    state.currentPage = 1;
    renderTable();

    renderChart(chartRes);
    renderSummary(summaryRes);

    // 更新时间戳
    lastUpdate.textContent = `已更新 ${formatTime(new Date())}`;

  } catch (e) {
    console.error('刷新数据失败:', e);
    overviewGrid.innerHTML = `<div class="loading">❌ 加载失败: ${e.message}</div>`;
    tableBody.innerHTML = `<tr><td colspan="5" class="loading-cell">❌ 加载失败: ${e.message}</td></tr>`;
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

function renderTable() {
  const data = state.allData;
  tableCount.textContent = `${data.length} 条`;

  if (!data.length) {
    tableBody.innerHTML = '<tr><td colspan="5" class="loading-cell">📭 暂无数据</td></tr>';
    updatePagination(0);
    return;
  }

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

  const total = sorted.length;
  const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
  if (state.currentPage > totalPages) state.currentPage = totalPages;
  const start = (state.currentPage - 1) * state.pageSize;
  const pageData = sorted.slice(start, start + state.pageSize);

  let html = '';
  for (const row of pageData) {
    const displayVal = cpiToGrowth(row.value);
    const val = displayVal !== null
      ? (displayVal >= 0 ? '+' : '') + displayVal.toFixed(2)
      : 'N/A';
    const shortName = normName(row.indicator || '');
    html += `
      <tr>
        <td>${escapeHtml(row.date || '')}</td>
        <td title="${escapeHtml(row.indicator || '')}">${escapeHtml(shortName)}</td>
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

function renderSummary(res) {
  if (!res || !res.data || !res.data.details) {
    document.getElementById('summary-grid').innerHTML = '<div class="loading">📭 无摘要数据</div>';
    return;
  }

  const details = res.data.details;
  // 合并同名指标（如食品烟酒跨周期两个名称）
  const { merged, order } = mergeSummaryDetails(details);
  let html = '';

  for (const name of order) {
    const info = merged[name];
    const trendIcon = info.trend === 'up' ? '📈' : info.trend === 'down' ? '📉' : '➡️';
    const latestVal = info.latest ? _fmtGrowth(info.latest.value) : 'N/A';
    const latestDate = info.latest ? info.latest.date : '';
    const meanVal = info.mean !== undefined ? _fmtGrowth(info.mean) : '--';
    const maxVal = info.max ? _fmtGrowth(info.max.value) : '--';
    const minVal = info.min ? _fmtGrowth(info.min.value) : '--';
    const volVal = info.volatility !== undefined ? info.volatility.toFixed(2) : '--';
    const stdVal = info.std !== undefined ? info.std.toFixed(2) : '--';

    function _fmtGrowth(v) {
      if (v === null || v === undefined) return '--';
      const g = cpiToGrowth(v);
      return (g >= 0 ? '+' : '') + g.toFixed(2);
    }

    html += `
      <div class="summary-card">
        <div class="indicator-name">${trendIcon} ${escapeHtml(name)}</div>
        <div class="value">${latestVal}</div>
        <div class="meta">${latestDate}</div>
        <div class="stats-list">
          <div class="stat-row"><span class="stat-label">均值</span><span class="stat-val">${meanVal}</span></div>
          <div class="stat-row"><span class="stat-label">最高</span><span class="stat-val">${maxVal}</span></div>
          <div class="stat-row"><span class="stat-label">最低</span><span class="stat-val">${minVal}</span></div>
          <div class="stat-row"><span class="stat-label">波动</span><span class="stat-val">${volVal}</span></div>
          <div class="stat-row"><span class="stat-label">标准差</span><span class="stat-val">${stdVal}</span></div>
        </div>
      </div>
    `;
  }

  document.getElementById('summary-grid').innerHTML = html;
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
    analysis: '深度分析',
    settings: '数据设置',
  };
  toolbarTitle.textContent = nameMap[sectionId] || sectionId;

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

/**
 * 对 summary details 按归一化名称合并统计值。
 */
function mergeSummaryDetails(details) {
  const merged = {};
  const order = [];
  for (const [fullName, info] of Object.entries(details)) {
    const shortName = normName(fullName);
    if (!merged[shortName]) {
      merged[shortName] = { ...info, _count: 1 };
      order.push(shortName);
    } else {
      // 合并统计：取范围更大的
      const existing = merged[shortName];
      existing._count++;
      existing.count += info.count || 0;
      // 日期范围取并集
      const oldRange = existing.date_range || '';
      const newRange = info.date_range || '';
      if (newRange && oldRange) {
        const oldStart = oldRange.split(' ~ ')[0];
        const oldEnd = oldRange.split(' ~ ')[1];
        const newStart = newRange.split(' ~ ')[0];
        const newEnd = newRange.split(' ~ ')[1];
        existing.date_range = `${oldStart < newStart ? oldStart : newStart} ~ ${oldEnd > newEnd ? oldEnd : newEnd}`;
      } else if (newRange && !oldRange) {
        existing.date_range = newRange;
      }
      // latest 取最新日期
      if (info.latest && (!existing.latest || info.latest.date > existing.latest.date)) {
        existing.latest = info.latest;
      }
      // 数值统计取合并后的
      if (info.mean !== undefined) {
        existing.mean = (existing.mean || 0) + info.mean;  // 简化处理，会偏
      }
      if (info.max && (!existing.max || info.max.value > existing.max.value)) {
        existing.max = info.max;
      }
      if (info.min && (!existing.min || info.min.value < existing.min.value)) {
        existing.min = info.min;
      }
      if (info.volatility !== undefined) {
        const v1 = existing.volatility || 0;
        const v2 = info.volatility || 0;
        existing.volatility = Math.max(v1, v2);
      }
    }
  }
  return { merged, order };
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

/* ── 指标排序（总CPI → 核心CPI → 八大标准分项） ──── */

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
 * 按预设顺序对 indicator 数组排序
 * @param {string[]} names - 指标名称数组
 * @param {string[]} items - 要排序的完整对象数组，每个对象有 .indicator 或 .name 属性
 * @param {string} keyField - 对象中的名称字段，默认 'indicator'
 * @returns {Array} 排序后的新数组
 */
function sortByIndicatorOrder(items, keyField = 'indicator') {
  const orderMap = new Map();
  // 合并两个周期的顺序
  const allOrders = [...INDICATOR_ORDER, ...INDICATOR_ORDER_2021];
  allOrders.forEach((name, i) => {
    if (!orderMap.has(name)) orderMap.set(name, i);
  });
  // 也支持按简名匹配
  function getOrder(item) {
    const name = item[keyField] || '';
    if (orderMap.has(name)) return orderMap.get(name);
    // 模糊匹配：去掉括号内容
    const stripped = name.replace(/\(.*?\)/g, '').trim();
    for (const [key, idx] of orderMap) {
      if (key.replace(/\(.*?\)/g, '').trim() === stripped) return idx;
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

  // 刷新
  refreshBtn.addEventListener('click', refreshAll);

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
      if (isNaN(months)) return;
      // 计算预设时间段
      const endYM = getLatestMonth();
      const startYM = subtractMonths(endYM, months - 1);
      if (periodStart) periodStart.value = startYM;
      if (periodEnd) periodEnd.value = endYM;
      // 高亮当前按钮
      periodPresetBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      refreshAll();
    });
  });

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

      document.querySelectorAll('#data-table th[data-sort]').forEach(h => {
        h.classList.remove('sort-asc', 'sort-desc');
      });
      th.classList.add(state.sortAsc ? 'sort-asc' : 'sort-desc');

      state.currentPage = 1;
      renderTable();
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
  // 兜底：当前月份 - 1 个月
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth(); // 0-indexed
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
    const icon = e.target.closest('.tooltip-icon');
    if (!icon || icon === activeIcon) return;
    activeIcon = icon;

    const idx = parseInt(icon.dataset.tipIdx, 10);
    if (isNaN(idx)) return;
    const content = getTooltipContent(idx);
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
    const icon = e.target.closest('.tooltip-icon');
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
  const startYM = subtractMonths(endYM, 11); // 12个月 - 1
  if (periodStart) periodStart.value = startYM;
  if (periodEnd) periodEnd.value = endYM;
  state.selectedPeriod = `${startYM}-${endYM}`;
}

/* 暴露 switchSection 给全局，用于 HTML 中的 onclick */
window.switchSection = switchSection;

/* ══════════════════════════════════════════════════════
   启动
   ══════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', init);
