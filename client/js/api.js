/**
 * THEIA · API 客户端
 *
 * 封装所有与后端 API 的通信。
 * 所有函数返回 Promise<json>。
 */

const API_BASE_CPI = '/api/v1/cpi';
const API_BASE_PPI = '/api/v1/ppi';
const API_BASE_MS = '/api/v1/money-supply';

/**
 * 通用请求函数
 */
async function apiRequest(url, options = {}) {
  const resp = await fetch(`${API_BASE_CPI}${url}`, {
    headers: { 'Accept': 'application/json' },
    ...options,
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${resp.status}`);
  }

  const json = await resp.json();
  if (!json.success && json.error) {
    throw new Error(json.error);
  }
  return json;
}

/**
 * 构建查询字符串
 */
function qs(params) {
  const parts = [];
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') {
      parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
    }
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

/**
 * 获取总体概览
 * GET /api/v1/cpi/overview
 */
export async function fetchOverview(params = {}) {
  return apiRequest(`/overview${qs(params)}`);
}

/**
 * 获取指标列表
 * GET /api/v1/cpi/indicators
 */
export async function fetchIndicators() {
  return apiRequest('/indicators');
}


// ═══════════════════════════════════════════════════════
//  PPI API
// ═══════════════════════════════════════════════════════

/**
 * 通用 PPI 请求
 */
async function ppiRequest(url, options = {}) {
  const resp = await fetch(`${API_BASE_PPI}${url}`, {
    headers: { 'Accept': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${resp.status}`);
  }
  const json = await resp.json();
  if (!json.success && json.error) {
    throw new Error(json.error);
  }
  return json;
}

/**
 * 获取 PPI 总体概览
 * GET /api/v1/ppi/overview
 */
export async function fetchPpiOverview(params = {}) {
  return ppiRequest(`/overview${qs(params)}`);
}

/**
 * 获取 PPI 指标列表
 * GET /api/v1/ppi/indicators
 */
export async function fetchPpiIndicators() {
  return ppiRequest('/indicators');
}

/**
 * 获取 PPI 原始数据
 * GET /api/v1/ppi/data
 */
export async function fetchPpiData(params = {}) {
  return ppiRequest(`/data${qs(params)}`);
}

/**
 * 获取 PPI 图表数据
 * GET /api/v1/ppi/chart
 */
export async function fetchPpiChart(params = {}) {
  return ppiRequest(`/chart${qs(params)}`);
}

/**
 * 获取 PPI 分组列表
 * GET /api/v1/ppi/groups
 */
export async function fetchPpiGroups() {
  return ppiRequest('/groups');
}

/**
 * 获取原始数据
 * GET /api/v1/cpi/data
 */
export async function fetchData(params = {}) {
  return apiRequest(`/data${qs(params)}`);
}

/**
 * 获取图表数据
 * GET /api/v1/cpi/chart
 */
export async function fetchChart(params = {}) {
  return apiRequest(`/chart${qs(params)}`);
}

/**
 * 获取分组列表
 * GET /api/v1/cpi/groups
 */
export async function fetchGroups() {
  return apiRequest('/groups');
}


// ═══════════════════════════════════════════════════════
//  货币供应量 (Money Supply) API
// ═══════════════════════════════════════════════════════

/**
 * 通用货币供应量请求
 */
async function msRequest(url, options = {}) {
  const resp = await fetch(`${API_BASE_MS}${url}`, {
    headers: { 'Accept': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${resp.status}`);
  }
  const json = await resp.json();
  if (!json.success && json.error) {
    throw new Error(json.error);
  }
  return json;
}

/**
 * 获取货币供应量总体概览
 * GET /api/v1/money-supply/overview
 */
export async function fetchMsOverview(params = {}) {
  return msRequest(`/overview${qs(params)}`);
}

/**
 * 获取货币供应量指标列表
 * GET /api/v1/money-supply/indicators
 */
export async function fetchMsIndicators() {
  return msRequest('/indicators');
}

/**
 * 获取货币供应量原始数据
 * GET /api/v1/money-supply/data
 */
export async function fetchMsData(params = {}) {
  return msRequest(`/data${qs(params)}`);
}

/**
 * 获取货币供应量图表数据
 * GET /api/v1/money-supply/chart
 */
export async function fetchMsChart(params = {}) {
  return msRequest(`/chart${qs(params)}`);
}

/**
 * 获取货币供应量分组列表
 * GET /api/v1/money-supply/groups
 */
export async function fetchMsGroups() {
  return msRequest('/groups');
}

/**
 * 获取货币供应量同比增长数据（表格专用）
 * GET /api/v1/money-supply/yoy
 */
export async function fetchMsYoy(params = {}) {
  return msRequest(`/yoy${qs(params)}`);
}
