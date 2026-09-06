/**
 * HTTP请求封装
 * 包含智能缓存层：请求去重 + 内存缓存 + 按接口配置过期时间
 */
const config = require('./config.js')
const { formatLocalDate, formatLocalDateTime } = require('./date.js')
const {
  ensureAuthenticated,
  getAccessToken,
  clearAuthSession,
  clearPersistentBusinessCache
} = require('./auth.js')

/**
 * 将后端返回的相对 API 地址补全为绝对地址。
 * 不解析、不重组 query，避免破坏签名参数的原始顺序和编码。
 */
function resolveApiUrl(value) {
  if (!value) return ''
  const url = String(value)
  if (/^https?:\/\//i.test(url)) return url
  return `${config.API_BASE_URL}${url.startsWith('/') ? '' : '/'}${url}`
}

// ========== 缓存配置 ==========
const CACHE_CONFIG = {
  '/api/v1/dashboard/today': 10 * 60 * 1000,        // 10分钟
  '/api/v1/oura/sleep/grouped': 10 * 60 * 1000,     // 10分钟
  '/api/v1/oura/sleep': 10 * 60 * 1000,             // 10分钟
  '/api/v1/oura/readiness': 10 * 60 * 1000,         // 10分钟
  '/api/v1/oura/activity': 10 * 60 * 1000,          // 10分钟
  '/api/v1/oura/stress': 10 * 60 * 1000,            // 10分钟
  '/api/v1/oura/spo2': 10 * 60 * 1000,              // 10分钟
  '/api/v1/oura/heartrate-detail': 10 * 60 * 1000,  // 10分钟
  '/api/v1/training/today': 30 * 60 * 1000,         // 30分钟
  '/api/v1/training/weekly': 10 * 60 * 1000,        // 10分钟
  '/api/v1/training/history': 10 * 60 * 1000,       // 10分钟
  '/api/v1/ai/recommendation': 10 * 60 * 1000,      // 10分钟
  '/api/v1/nutrition/meals': 30 * 60 * 1000,        // 30分钟
  '/api/v1/nutrition/daily': 30 * 60 * 1000,        // 30分钟
  '/api/v1/nutrition/weekly': 10 * 60 * 1000,       // 10分钟
  '/api/v1/trends/overview': 10 * 60 * 1000,        // 10分钟
  'default': 10 * 60 * 1000                         // 默认10分钟
}

// 内存缓存存储
const requestCache = {}
const toastTimestamps = {}
let authenticationRefreshPromise = null

/**
 * 生成缓存Key
 */
function generateCacheKey(method, url, data) {
  const keys = Object.keys(data).sort()
  const params = keys.length > 0 ? `?${keys.map(k => `${encodeURIComponent(k)}=${encodeURIComponent(data[k])}`).join('&')}` : ''
  return `${method}:${url}${params}`
}

/**
 * 获取接口的缓存过期时间
 */
function getCacheTTL(url) {
  // 精确匹配
  if (CACHE_CONFIG[url]) {
    return CACHE_CONFIG[url]
  }
  // 前缀匹配（处理带参数的URL如 /api/v1/nutrition/daily/2025-01-01）
  for (const key in CACHE_CONFIG) {
    if (url.startsWith(key)) {
      return CACHE_CONFIG[key]
    }
  }
  return CACHE_CONFIG['default']
}

/**
 * 检查缓存是否有效
 */
function isCacheValid(cacheKey, url) {
  const cached = requestCache[cacheKey]
  if (!cached) return false

  const ttl = getCacheTTL(url)
  const isValid = Date.now() - cached.timestamp < ttl

  if (!isValid && !cached.pending) {
    delete requestCache[cacheKey]
  }

  return isValid
}

/**
 * 清除所有缓存
 */
function clearAllCache() {
  Object.keys(requestCache).forEach(key => delete requestCache[key])
  console.log('[Cache] 已清除所有缓存')
}

/**
 * 清除指定URL的缓存
 */
function clearCache(url) {
  Object.keys(requestCache).forEach(key => {
    if (key.includes(url)) {
      delete requestCache[key]
      console.log(`[Cache] 已清除缓存: ${key}`)
    }
  })
}

function showThrottledToast(key, title, duration = 2000) {
  const now = Date.now()
  const throttleWindow = duration + 300

  if (toastTimestamps[key] && now - toastTimestamps[key] < throttleWindow) {
    return
  }

  toastTimestamps[key] = now
  wx.showToast({
    title,
    icon: 'none',
    duration
  })
}

function syncAppAuthentication(session = null) {
  try {
    const app = getApp()
    if (app && typeof app.applyAuthSession === 'function') {
      app.applyAuthSession(session)
    }
  } catch (error) {
    console.warn('[Auth] 同步全局认证状态失败:', error)
  }
}

function notifyAppAuthenticationFailure(error) {
  try {
    const app = getApp()
    if (!app) return
    app.globalData.authError = error?.message || '登录状态异常，请稍后重试'
    if (typeof app.notifyAuthFailure === 'function') {
      app.notifyAuthFailure(error)
    }
  } catch (syncError) {
    console.warn('[Auth] 同步认证失败状态异常:', syncError)
  }
}

function createRequestError(response, authRetryCount = 0) {
  const statusCode = response.statusCode
  const data = response.data || {}
  const backendMessage = data.detail || data.message || ''
  const retryAfter = response.header?.['Retry-After'] || response.header?.['retry-after'] || ''
  const rateLimitMessage = retryAfter
    ? `操作过于频繁，请 ${retryAfter} 秒后重试`
    : '操作过于频繁，请稍后重试'
  const messages = {
    401: authRetryCount > 0 ? '登录状态异常，请稍后重试' : '登录状态已失效，正在重新连接',
    403: '当前微信账号未获授权',
    422: '请求结构错误，请联系开发者',
    429: rateLimitMessage,
    500: '服务端异常，请稍后重试',
    502: '微信认证服务暂时不可用',
    503: '服务暂不可用'
  }

  if (statusCode === 422) {
    console.error('[API Contract Error]', data)
  }

  return {
    code: statusCode,
    statusCode,
    data,
    retryAfter,
    message: messages[statusCode] || backendMessage || '请求失败'
  }
}

function refreshAuthenticationAfter401(failedToken) {
  const currentToken = getAccessToken()
  if (currentToken && failedToken && currentToken !== failedToken) {
    return Promise.resolve(currentToken)
  }
  if (authenticationRefreshPromise) return authenticationRefreshPromise

  clearAuthSession()
  clearAllCache()
  clearPersistentBusinessCache()
  syncAppAuthentication(null)

  const promise = ensureAuthenticated({ force: true })
    .then(session => {
      syncAppAuthentication(session)
      return session.accessToken
    })
    .catch(error => {
      notifyAppAuthenticationFailure(error)
      throw error
    })
    .finally(() => {
      if (authenticationRefreshPromise === promise) authenticationRefreshPromise = null
    })

  authenticationRefreshPromise = promise
  return promise
}

function sendRequest({ url, method, data, timeout, needAuth, authRetryCount }) {
  const tokenUsed = needAuth ? getAccessToken() : ''
  const header = { 'Content-Type': 'application/json' }
  if (tokenUsed) header.Authorization = `Bearer ${tokenUsed}`

  console.log(`[API Request] ${method} ${url}`)

  return new Promise((resolve, reject) => {
    wx.request({
      url: resolveApiUrl(url),
      method,
      data,
      header,
      timeout,
      success(response) {
        console.log(`[API Response] ${method} ${url}`, response.statusCode)
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data)
          return
        }
        reject({ ...createRequestError(response, authRetryCount), tokenUsed })
      },
      fail(error) {
        console.error(`[API Error] ${method} ${url}`, error)
        const isTimeout = /timeout/i.test(error.errMsg || '')
        reject({
          code: isTimeout ? 'TIMEOUT' : -1,
          message: isTimeout ? '请求超时，请稍后重试' : '网络请求失败，请检查网络连接',
          detail: error.errMsg || ''
        })
        showThrottledToast('network-error', '网络请求失败')
      }
    })
  })
}

/**
 * 发起HTTP请求
 * @param {Object} options 请求配置
 * @param {String} options.url 请求路径（相对路径）
 * @param {String} options.method 请求方法
 * @param {Object} options.data 请求数据
 * @param {Boolean} options.needAuth 是否需要认证（默认true）
 * @returns {Promise}
 */
async function request(options) {
  const {
    url,
    method = 'GET',
    data = {},
    needAuth = true,
    timeout = config.REQUEST_TIMEOUT,
    _authRetryCount = 0
  } = options

  if (needAuth) await ensureAuthenticated()

  try {
    return await sendRequest({
      url,
      method,
      data,
      timeout,
      needAuth,
      authRetryCount: _authRetryCount
    })
  } catch (error) {
    if (needAuth && error?.code === 401 && _authRetryCount === 0) {
      await refreshAuthenticationAfter401(error.tokenUsed)
      return request({ ...options, _authRetryCount: 1 })
    }

    if (error?.code === 401 && _authRetryCount > 0) {
      clearAuthSession()
      syncAppAuthentication(null)
      error.message = '登录状态异常，请稍后重试'
      notifyAppAuthenticationFailure(error)
    }

    if (error?.code === 403) {
      showThrottledToast('auth-forbidden', '当前微信账号未获授权', 2600)
    }
    throw error
  }
}

/**
 * GET请求（带缓存）
 * @param {String} url 请求路径
 * @param {Object} data 请求参数
 * @param {Boolean} needAuth 是否需要认证
 * @param {Boolean} forceRefresh 是否强制刷新（跳过缓存）
 */
function get(url, data = {}, needAuth = true, forceRefresh = false) {
  if (needAuth) {
    return ensureAuthenticated().then(() => getWithCache(url, data, needAuth, forceRefresh))
  }
  return getWithCache(url, data, needAuth, forceRefresh)
}

function getWithCache(url, data, needAuth, forceRefresh) {
  const cacheKey = generateCacheKey('GET', url, data)

  // 非强制刷新时，检查缓存
  if (!forceRefresh && isCacheValid(cacheKey, url)) {
    console.log(`[Cache Hit] ${url}`)
    return Promise.resolve(requestCache[cacheKey].data)
  }

  // 检查是否有进行中的相同请求（请求去重）
  if (requestCache[cacheKey] && requestCache[cacheKey].pending) {
    console.log(`[Cache Pending] ${url} - 复用进行中的请求`)
    return requestCache[cacheKey].pending
  }

  // 以条目身份隔离失效前后的请求，旧响应不能重新填充已清理的缓存。
  const entry = { ...requestCache[cacheKey] }
  const pending = request({
    url,
    method: 'GET',
    data,
    needAuth
  }).then(result => {
    if (requestCache[cacheKey] === entry) {
      entry.data = result
      entry.timestamp = Date.now()
      entry.pending = null
    }
    return result
  }).catch(err => {
    if (requestCache[cacheKey] === entry) {
      entry.pending = null
    }
    throw err
  })

  entry.pending = pending
  requestCache[cacheKey] = entry

  return pending
}

/**
 * POST请求
 */
function post(url, data = {}, needAuth = true) {
  return request({
    url,
    method: 'POST',
    data,
    needAuth
  })
}

/**
 * 获取今日训练数据
 */
function getTodayTraining() {
  return get('/api/v1/training/today')
}

/**
 * 获取本周训练总结
 */
function getWeeklyTraining() {
  return get('/api/v1/training/weekly')
}

/**
 * 获取训练历史
 * @param {Object} params 查询参数
 * @param {String} params.start_date 开始日期
 * @param {String} params.end_date 结束日期
 * @param {Number} params.page 页码
 * @param {Number} params.page_size 每页数量
 */
function getTrainingHistory(params = {}) {
  return get('/api/v1/training/history', params)
}

/**
 * 获取指定日期的训练总结
 * @param {String} date 日期 YYYY-MM-DD
 */
function getDailySummary(date) {
  return get(`/api/v1/training/daily/${date}`)
}

/**
 * 获取今日AI建议
 */
function getTodayRecommendation() {
  return get('/api/v1/ai/recommendation/today')
}

/**
 * 获取指定日期的AI建议
 * @param {String} date 日期 YYYY-MM-DD
 */
function getRecommendation(date) {
  return get(`/api/v1/ai/recommendation/${date}`)
}

/**
 * 重新生成AI建议
 * @param {String} date 日期 YYYY-MM-DD
 * @param {String} provider AI模型（可选）
 */
function regenerateRecommendation(date, provider = null) {
  return request({
    url: '/api/v1/ai/regenerate',
    method: 'POST',
    data: { date, provider },
    timeout: 60000
  })
}

/**
 * 获取用户信息
 */
function getUserInfo() {
  return get('/api/v1/user/profile')
}

/**
 * 更新用户信息
 * @param {Object} data 用户数据
 */
function updateUserInfo(data) {
  return request({
    url: '/api/v1/user/profile',
    method: 'PUT',
    data
  })
}

/**
 * 获取Polar授权状态
 */
function getPolarAuthStatus() {
  return get('/api/v1/polar/status')
}

/**
 * 手动同步Polar数据
 */
function syncPolarData(days = 7) {
  return post('/api/v1/polar/sync', { days })
}

/**
 * 获取Dashboard今日数据（包含训练、睡眠、准备度、活动）
 */
function getDashboard() {
  return get('/api/v1/dashboard/today')
}

/**
 * 获取综合趋势（包含 nutrition 五组数组）
 */
function getTrendsOverview(startDate, endDate) {
  return get('/api/v1/trends/overview', {
    start_date: startDate,
    end_date: endDate
  })
}

/**
 * 获取Oura睡眠数据
 * @param {Number} days 获取天数（默认7天）
 */
function getOuraSleep(days = 7) {
  return get('/api/v1/oura/sleep', { days })
}

/**
 * 获取Oura睡眠数据（分组版，支持多片段）
 * 返回按天分组的睡眠数据，包含主睡眠和午睡片段
 * @param {Number} days 获取天数（默认7天）
 */
function getOuraSleepGrouped(days = 7) {
  return get('/api/v1/oura/sleep/grouped', { days })
}

/**
 * 获取Oura准备度数据
 * @param {Number} days 获取天数（默认7天）
 */
function getOuraReadiness(days = 7) {
  return get('/api/v1/oura/readiness', { days })
}

/**
 * 获取Oura活动数据
 * @param {Number} days 获取天数（默认7天）
 */
function getOuraActivity(days = 7) {
  return get('/api/v1/oura/activity', { days })
}

/**
 * 获取Oura血氧数据
 * @param {Number} days 获取天数（默认7天）
 */
function getOuraSpo2(days = 7) {
  return get('/api/v1/oura/spo2', { days })
}

/**
 * 获取Oura压力数据
 * @param {Number} days 获取天数（默认7天）
 */
function getOuraStress(days = 7) {
  return get('/api/v1/oura/stress', { days })
}

/**
 * 获取Oura心率详情（包含最低心率时间点、恢复质量等）
 * @param {String} day 日期 YYYY-MM-DD
 */
function getOuraHeartrateDetail(day) {
  return get('/api/v1/oura/heartrate-detail', { day })
}

/**
 * 获取多天心率详情（用于趋势图）
 * @param {Number} days 获取天数（默认7天）
 */
async function getOuraHeartrateDetails(days = 7) {
  const today = new Date()
  const requests = []

  // 构建所有日期的请求
  for (let i = 0; i < days; i++) {
    const date = new Date(today)
    date.setDate(date.getDate() - i)
    const dayStr = formatLocalDate(date)

    // 并行请求所有日期
    requests.push(
      get('/api/v1/oura/heartrate-detail', { day: dayStr })
        .then(data => {
          if (data && data.lowest_hr) {
            return { day: dayStr, ...data }
          }
          return null
        })
        .catch(e => {
          console.warn(`获取${dayStr}心率详情失败:`, e)
          return null
        })
    )
  }

  // 并行执行所有请求
  const results = await Promise.all(requests)

  // 过滤空值并排序
  return results.filter(r => r !== null).sort((a, b) => a.day.localeCompare(b.day))
}

/**
 * 同步Oura数据
 */
function syncOuraData(days = 7, force = false) {
  return post('/api/v1/oura/sync', { days, force })
}

/**
 * 获取训练历史（用于趋势）
 * @param {Number} days 获取天数
 */
function getTrainingTrends(days = 7) {
  return get('/api/v1/training/history', { days })
}

// ========== 营养饮食相关 API ==========

/**
 * 上传餐食照片并分析
 * @param {String} filePath 图片临时路径
 * @param {String} mealType 餐次类型 breakfast/lunch/dinner/snack
 * @param {Object} options 餐食时间与备注
 */
async function uploadMeal(filePath, mealType, options = {}) {
  await ensureAuthenticated()
  return performMealUpload(filePath, mealType, options, 0)
}

function performMealUpload(filePath, mealType, options, authRetryCount) {
  return new Promise((resolve, reject) => {
    const tokenUsed = getAccessToken()
    const mealTime = formatLocalDateTime(options.mealTime || new Date())
    const notes = options.notes || ''

    wx.uploadFile({
      url: `${config.API_BASE_URL}/api/v1/nutrition/upload`,
      filePath: filePath,
      name: 'image',
      formData: {
        meal_type: mealType,
        meal_time: mealTime,
        notes
      },
      header: {
        'Authorization': `Bearer ${tokenUsed}`
      },
      timeout: 120000, // 120秒超时，AI分析需要较长时间
      success(res) {
        console.log('[Upload] Response status:', res.statusCode)
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            const data = JSON.parse(res.data)
            resolve(data)
          } catch (e) {
            reject({ code: -1, message: '解析响应失败' })
          }
        } else if (res.statusCode === 401 && authRetryCount === 0) {
          refreshAuthenticationAfter401(tokenUsed)
            .then(() => performMealUpload(filePath, mealType, options, 1))
            .then(resolve, reject)
        } else if (res.statusCode === 401) {
          clearAuthSession()
          syncAppAuthentication(null)
          const error = { code: 401, message: '登录状态异常，请稍后重试' }
          notifyAppAuthenticationFailure(error)
          reject(error)
        } else {
          let errorData = {}
          try {
            errorData = JSON.parse(res.data)
          } catch (e) {}
          reject(createRequestError({
            statusCode: res.statusCode,
            data: errorData,
            header: res.header || {}
          }, authRetryCount))
        }
      },
      fail(err) {
        console.error('[Upload] Error:', err)
        // 提供更详细的错误信息
        let errorMessage = '网络请求失败'
        if (err.errMsg) {
          if (err.errMsg.includes('timeout')) {
            errorMessage = '识图响应较慢，系统可能仍在处理，请稍后刷新饮食记录。'
          } else if (err.errMsg.includes('abort')) {
            errorMessage = '上传被中断'
          } else if (err.errMsg.includes('ssl') || err.errMsg.includes('certificate')) {
            errorMessage = '网络安全连接失败，请检查网络'
          } else if (err.errMsg.includes('fail')) {
            errorMessage = `网络错误: ${err.errMsg}`
          }
        }
        reject({
          code: err.errMsg && err.errMsg.includes('timeout') ? 'TIMEOUT' : -1,
          message: errorMessage,
          detail: err.errMsg
        })
      }
    })
  })
}

/**
 * 获取饮食记录列表
 */
function getMeals(params = {}) {
  return request({ url: '/api/v1/nutrition/meals', method: 'GET', data: params, needAuth: true })
}

/**
 * 获取单条饮食记录详情
 */
function getMealDetail(mealId) {
  return request({ url: `/api/v1/nutrition/meals/${mealId}`, method: 'GET', data: {}, needAuth: true })
}

/**
 * 查询餐食核心分析与未来饮食建议的异步状态。
 * 每次都跳过缓存，避免轮询读到旧状态。
 */
function getMealAnalysisStatus(mealId) {
  return request({
    url: `/api/v1/nutrition/meals/${mealId}/analysis-status`,
    method: 'GET',
    data: {},
    needAuth: true
  })
}

/**
 * 只生成饮食建议，不重复上传图片或重新执行识图。
 * 普通失败重试不传 force；只有用户明确重新生成时才传 force=true。
 */
function requestMealRecommendations(mealId, force = false) {
  const forceQuery = force ? '?force=true' : ''
  return request({
    url: `/api/v1/nutrition/meals/${mealId}/recommendations${forceQuery}`,
    method: 'POST',
    data: {},
    timeout: 30000
  })
}

/**
 * 删除饮食记录
 */
function deleteMeal(mealId) {
  return request({
    url: `/api/v1/nutrition/meals/${mealId}`,
    method: 'DELETE'
  })
}

/**
 * 重新分析饮食记录
 */
function reanalyzeMeal(mealId) {
  return request({
    url: `/api/v1/nutrition/meals/${mealId}/reanalyze`,
    method: 'POST',
    data: {},
    timeout: 120000
  })
}

/**
 * 按需生成餐食分享海报。普通生成允许服务端复用缓存，只有用户明确
 * 选择重新生成时才传 force=true。
 */
function generateMealPoster(mealId, force = false) {
  const forceQuery = force ? '?force=true' : ''
  return request({
    url: `/api/v1/nutrition/meals/${mealId}/poster${forceQuery}`,
    method: 'POST',
    data: {},
    timeout: 120000
  })
}

/**
 * 获取每日营养总结
 */
function getNutritionDaily(date) {
  return get(`/api/v1/nutrition/daily/${date}`)
}

// 别名，兼容旧代码
const getNutritionDailySummary = getNutritionDaily

/**
 * 获取每周营养趋势
 */
function getNutritionWeekly() {
  return get('/api/v1/nutrition/weekly')
}

module.exports = {
  request,
  get,
  post,
  resolveApiUrl,
  // 缓存工具
  clearAllCache,
  clearCache,
  getTodayTraining,
  getWeeklyTraining,
  getTrainingHistory,
  getTrainingTrends,
  getDailySummary,
  getTodayRecommendation,
  getRecommendation,
  regenerateRecommendation,
  getUserInfo,
  updateUserInfo,
  getPolarAuthStatus,
  syncPolarData,
  getDashboard,
  getTrendsOverview,
  getOuraSleep,
  getOuraSleepGrouped,
  getOuraReadiness,
  getOuraActivity,
  getOuraSpo2,
  getOuraStress,
  getOuraHeartrateDetail,
  getOuraHeartrateDetails,
  syncOuraData,
  // 营养饮食
  uploadMeal,
  getMeals,
  getMealDetail,
  getMealAnalysisStatus,
  requestMealRecommendations,
  deleteMeal,
  reanalyzeMeal,
  generateMealPoster,
  getNutritionDaily,
  getNutritionDailySummary,
  getNutritionWeekly
}
