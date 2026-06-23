/**
 * THEIA · CPI API 客户端
 *
 * 封装所有与后端 API 的通信。
 * 所有函数返回 Promise<json>。
 */

const API_BASE = '/api/v1/cpi';

/**
 * 通用请求函数
 */
async function apiRequest(url, options = {}) {
  const resp = await fetch(`${API_BASE}${url}`, {
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

/**
 * 获取原始数据
 * GET /api/v1/cpi/data
 */
export async function fetchData(params = {}) {
  return apiRequest(`/data${qs(params)}`);
}

/**
 * 获取统计摘要
 * GET /api/v1/cpi/summary
 */
export async function fetchSummary(params = {}) {
  return apiRequest(`/summary${qs(params)}`);
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
