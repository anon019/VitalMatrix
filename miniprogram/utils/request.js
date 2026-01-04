/**
 * HTTP请求封装
 * 包含智能缓存层：请求去重 + 内存缓存 + 按接口配置过期时间
 */
const config = require('./config.js')

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
  '/api/v1/training/today': 5 * 60 * 1000,          // 5分钟
  '/api/v1/training/weekly': 10 * 60 * 1000,        // 10分钟
  '/api/v1/training/history': 10 * 60 * 1000,       // 10分钟
  '/api/v1/ai/recommendation': 10 * 60 * 1000,      // 10分钟
  '/api/v1/nutrition/meals': 5 * 60 * 1000,         // 5分钟
  '/api/v1/nutrition/daily': 5 * 60 * 1000,         // 5分钟
  '/api/v1/nutrition/weekly': 10 * 60 * 1000,       // 10分钟
  'default': 5 * 60 * 1000                          // 默认5分钟
}

// 内存缓存存储
const requestCache = {}

/**
 * 生成缓存Key
 */
function generateCacheKey(method, url, data) {
  const params = Object.keys(data).length > 0 ? `?${JSON.stringify(data)}` : ''
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

  if (!isValid) {
    // 缓存过期，清理
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

/**
 * 发起HTTP请求
 * @param {Object} options 请求配置
 * @param {String} options.url 请求路径（相对路径）
 * @param {String} options.method 请求方法
 * @param {Object} options.data 请求数据
 * @param {Boolean} options.needAuth 是否需要认证（默认true）
 * @returns {Promise}
 */
function request(options) {
  return new Promise((resolve, reject) => {
    const {
      url,
      method = 'GET',
      data = {},
      needAuth = true
    } = options

    // 构建完整URL
    const fullUrl = `${config.API_BASE_URL}${url}`

    // 构建请求头
    const header = {
      'Content-Type': 'application/json'
    }

    // 添加认证token
    if (needAuth) {
      const token = wx.getStorageSync(config.TOKEN_KEY)
      if (token) {
        header['Authorization'] = `Bearer ${token}`
      } else {
        console.warn('未找到登录token，可能需要重新登录')
      }
    }

    console.log(`[API Request] ${method} ${url}`, data)

    wx.request({
      url: fullUrl,
      method,
      data,
      header,
      timeout: config.REQUEST_TIMEOUT,
      success(res) {
        console.log(`[API Response] ${method} ${url}`, res.statusCode, res.data)

        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else if (res.statusCode === 401) {
          // 认证失败，清除登录状态
          wx.removeStorageSync(config.TOKEN_KEY)
          wx.removeStorageSync(config.USER_INFO_KEY)

          reject({
            code: 401,
            message: '登录已失效，请重新登录'
          })

          // 提示用户重新登录
          wx.showToast({
            title: '登录已失效',
            icon: 'none'
          })

          // 触发重新登录
          setTimeout(() => {
            const app = getApp()
            if (app && app.autoLogin) {
              app.autoLogin()
            }
          }, 1500)
        } else {
          reject({
            code: res.statusCode,
            message: res.data.detail || res.data.message || '请求失败'
          })
        }
      },
      fail(err) {
        console.error(`[API Error] ${method} ${url}`, err)

        reject({
          code: -1,
          message: '网络请求失败，请检查网络连接'
        })

        wx.showToast({
          title: '网络请求失败',
          icon: 'none'
        })
      }
    })
  })
}

/**
 * GET请求（带缓存）
 * @param {String} url 请求路径
 * @param {Object} data 请求参数
 * @param {Boolean} needAuth 是否需要认证
 * @param {Boolean} forceRefresh 是否强制刷新（跳过缓存）
 */
function get(url, data = {}, needAuth = true, forceRefresh = false) {
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

  // 发起新请求
  const pending = request({
    url,
    method: 'GET',
    data,
    needAuth
  }).then(result => {
    // 缓存成功的响应
    requestCache[cacheKey] = {
      data: result,
      timestamp: Date.now(),
      pending: null
    }
    console.log(`[Cache Set] ${url}`)
    return result
  }).catch(err => {
    // 请求失败，清除pending状态
    if (requestCache[cacheKey]) {
      requestCache[cacheKey].pending = null
    }
    throw err
  })

  // 记录pending请求
  requestCache[cacheKey] = {
    ...requestCache[cacheKey],
    pending
  }

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
 * 简易登录（单用户模式）
 */
function login() {
  return post('/api/v1/auth/simple-login', {}, false)
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
  return post('/api/v1/ai/regenerate', { date, provider })
}

/**
 * 获取用户信息
 */
function getUserInfo() {
  return get('/api/v1/user/info')
}

/**
 * 更新用户信息
 * @param {Object} data 用户数据
 */
function updateUserInfo(data) {
  return post('/api/v1/user/update', data)
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
    const dayStr = date.toISOString().split('T')[0]

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
 */
function uploadMeal(filePath, mealType) {
  return new Promise((resolve, reject) => {
    const token = wx.getStorageSync(config.TOKEN_KEY)

    wx.uploadFile({
      url: `${config.API_BASE_URL}/api/v1/nutrition/upload`,
      filePath: filePath,
      name: 'image',
      formData: {
        meal_type: mealType
      },
      header: {
        'Authorization': `Bearer ${token}`
      },
      timeout: 120000, // 120秒超时，AI分析需要较长时间
      success(res) {
        console.log('[Upload] Response:', res)
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            const data = JSON.parse(res.data)
            resolve(data)
          } catch (e) {
            reject({ code: -1, message: '解析响应失败' })
          }
        } else {
          let errorMsg = '上传失败'
          try {
            const errData = JSON.parse(res.data)
            errorMsg = errData.detail || errData.message || errorMsg
          } catch (e) {}
          reject({ code: res.statusCode, message: errorMsg })
        }
      },
      fail(err) {
        console.error('[Upload] Error:', err)
        // 提供更详细的错误信息
        let errorMessage = '网络请求失败'
        if (err.errMsg) {
          if (err.errMsg.includes('timeout')) {
            errorMessage = 'AI分析超时，请稍后重试\n提示：选择较小的图片可加快分析速度'
          } else if (err.errMsg.includes('abort')) {
            errorMessage = '上传被中断'
          } else if (err.errMsg.includes('ssl') || err.errMsg.includes('certificate')) {
            errorMessage = '网络安全连接失败，请检查网络'
          } else if (err.errMsg.includes('fail')) {
            errorMessage = `网络错误: ${err.errMsg}`
          }
        }
        reject({ code: -1, message: errorMessage, detail: err.errMsg })
      }
    })
  })
}

/**
 * 获取饮食记录列表
 */
function getMeals(params = {}) {
  return get('/api/v1/nutrition/meals', params)
}

/**
 * 获取单条饮食记录详情
 */
function getMealDetail(mealId) {
  return get(`/api/v1/nutrition/meals/${mealId}`)
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
  return post(`/api/v1/nutrition/meals/${mealId}/reanalyze`)
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
  login,
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
  deleteMeal,
  reanalyzeMeal,
  getNutritionDaily,
  getNutritionDailySummary,
  getNutritionWeekly
}
