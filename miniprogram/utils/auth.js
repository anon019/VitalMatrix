/**
 * 小程序固定主用户静默认证。
 *
 * 微信 code 只在内存中使用一次；认证结果以单个 session 对象原子写入，
 * 不保存 Web 密码、OpenID，也不在客户端写死用户 ID。
 */
const config = require('./config.js')

const BUSINESS_STORAGE_KEYS = [
  'lastRefreshTime',
  'trendsLastRefresh',
  'nutritionLastRefresh',
  'nutritionNeedsRefresh',
  'aiLastRefresh',
  'settingsLastRefresh'
]

const BUSINESS_STORAGE_PREFIXES = ['mealPoster:']
let authenticationPromise = null

function removeStorageKeys(keys) {
  keys.forEach(key => wx.removeStorageSync(key))
}

function clearLegacyAuthenticationStorage() {
  removeStorageKeys([
    config.TOKEN_KEY,
    config.USER_INFO_KEY,
    config.USER_ID_KEY,
    config.AUTH_MODE_KEY,
    config.LEGACY_AUTH_MODE_KEY,
    config.AUTH_SESSION_KEY
  ])
}

function clearPersistentBusinessCache() {
  removeStorageKeys(BUSINESS_STORAGE_KEYS)

  if (typeof wx.getStorageInfoSync !== 'function') return
  const storageInfo = wx.getStorageInfoSync() || {}
  const keys = Array.isArray(storageInfo.keys) ? storageInfo.keys : []
  keys.forEach(key => {
    if (BUSINESS_STORAGE_PREFIXES.some(prefix => key.startsWith(prefix))) {
      wx.removeStorageSync(key)
    }
  })
}

/**
 * v2 迁移只删除已知认证键与业务缓存，不调用 clearStorage，避免影响
 * 用户尚未上传的本地草稿或其他无关本地状态。
 */
function migrateAuthStorage() {
  const currentVersion = Number(wx.getStorageSync(config.AUTH_STORAGE_VERSION_KEY) || 0)
  if (currentVersion === config.AUTH_STORAGE_VERSION) return false

  clearLegacyAuthenticationStorage()
  clearPersistentBusinessCache()
  wx.setStorageSync(config.AUTH_STORAGE_VERSION_KEY, config.AUTH_STORAGE_VERSION)
  console.log(`[Auth] 本地认证存储已迁移到 v${config.AUTH_STORAGE_VERSION}`)
  return true
}

function getAuthSession() {
  const stored = wx.getStorageSync(config.AUTH_SESSION_KEY)
  if (!stored || typeof stored !== 'object') return null
  return {
    ...stored,
    accessToken: stored.access_token || stored.accessToken || '',
    expiresIn: Number(stored.expires_in || stored.expiresIn || 0),
    authMode: stored.auth_mode || stored.authMode || '',
    loginAt: Number(stored.login_at || stored.loginAt || 0),
    expiresAt: Number(stored.expires_at || stored.expiresAt || 0)
  }
}

function isAuthSessionValid(session = getAuthSession()) {
  if (!session || !session.accessToken) return false
  if (session.authMode !== config.AUTH_MODE) return false

  const expiresAt = Number(session.expiresAt || 0)
  return expiresAt > Date.now() + config.AUTH_EXPIRY_SKEW_MS
}

function getAccessToken() {
  const session = getAuthSession()
  return session && session.accessToken ? session.accessToken : ''
}

function clearAuthSession() {
  clearLegacyAuthenticationStorage()
}

function createAuthError(statusCode, data = {}, header = {}) {
  const backendMessage = data?.detail || data?.message || ''
  const retryAfter = header['Retry-After'] || header['retry-after'] || ''
  const rateLimitMessage = retryAfter
    ? `操作过于频繁，请 ${retryAfter} 秒后重试`
    : '操作过于频繁，请稍后重试'
  const messages = {
    401: '登录状态异常，请稍后重试',
    403: '当前微信账号未获授权',
    422: '认证请求结构错误，请联系开发者',
    429: rateLimitMessage,
    500: '服务端异常，请稍后重试',
    502: '微信认证服务暂时不可用',
    503: '服务暂不可用'
  }

  return {
    code: statusCode,
    statusCode,
    data,
    retryAfter,
    message: messages[statusCode] || backendMessage || '数据连接失败，请稍后重试'
  }
}

function getWechatCode() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(result) {
        if (!result.code) {
          reject({ code: 'WECHAT_LOGIN_FAILED', message: '微信静默登录失败，请稍后重试' })
          return
        }
        resolve(result.code)
      },
      fail(error) {
        reject({
          code: 'WECHAT_LOGIN_FAILED',
          message: '微信静默登录失败，请稍后重试',
          detail: error.errMsg || ''
        })
      }
    })
  })
}

function exchangeWechatCode(code) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${config.API_BASE_URL}/api/v1/auth/miniprogram-login`,
      method: 'POST',
      data: { code },
      header: { 'Content-Type': 'application/json' },
      timeout: config.REQUEST_TIMEOUT,
      success(response) {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data)
          return
        }
        reject(createAuthError(response.statusCode, response.data, response.header || {}))
      },
      fail(error) {
        const isTimeout = /timeout/i.test(error.errMsg || '')
        reject({
          code: isTimeout ? 'TIMEOUT' : -1,
          message: isTimeout ? '微信认证响应超时，请稍后重试' : '网络连接失败，请稍后重试',
          detail: error.errMsg || ''
        })
      }
    })
  })
}

function persistAuthSession(response) {
  if (!response?.access_token || response.auth_mode !== config.AUTH_MODE) {
    throw {
      code: 'INVALID_AUTH_RESPONSE',
      message: '认证响应异常，请稍后重试'
    }
  }

  const expiresIn = Math.max(0, Number(response.expires_in || 0))
  if (!expiresIn) {
    throw {
      code: 'INVALID_AUTH_RESPONSE',
      message: '认证有效期异常，请稍后重试'
    }
  }

  const loginAt = Date.now()
  const storedSession = {
    access_token: response.access_token,
    expires_in: expiresIn,
    auth_mode: response.auth_mode,
    login_at: loginAt,
    expires_at: loginAt + expiresIn * 1000
  }

  // 单 key 写入，避免 token 与过期时间只更新一半。
  wx.setStorageSync(config.AUTH_SESSION_KEY, storedSession)
  removeStorageKeys([
    config.TOKEN_KEY,
    config.USER_INFO_KEY,
    config.USER_ID_KEY,
    config.AUTH_MODE_KEY,
    config.LEGACY_AUTH_MODE_KEY
  ])

  return {
    accessToken: storedSession.access_token,
    expiresIn: storedSession.expires_in,
    authMode: storedSession.auth_mode,
    loginAt: storedSession.login_at,
    expiresAt: storedSession.expires_at,
    userId: response.user_id || '',
    isNewUser: response.is_new_user === true
  }
}

async function performSilentLogin() {
  let lastError = null

  // 微信 code 无效时只重新获取一次；其他错误均不自动重试。
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const code = await getWechatCode()
    try {
      const response = await exchangeWechatCode(code)
      return persistAuthSession(response)
    } catch (error) {
      lastError = error
      if (error?.code !== 401 || attempt === 1) throw error
      console.warn('[Auth] 微信 code 无效，重新获取一次')
    }
  }

  throw lastError
}

/**
 * 全局唯一认证入口。多个页面和 401 刷新始终等待同一个 Promise。
 */
function ensureAuthenticated(options = {}) {
  const { force = false } = options
  const session = getAuthSession()
  if (!force && isAuthSessionValid(session)) return Promise.resolve(session)
  if (authenticationPromise) return authenticationPromise

  if (force || session) clearAuthSession()

  const promise = performSilentLogin().finally(() => {
    if (authenticationPromise === promise) authenticationPromise = null
  })
  authenticationPromise = promise
  return promise
}

module.exports = {
  migrateAuthStorage,
  clearPersistentBusinessCache,
  clearAuthSession,
  getAuthSession,
  getAccessToken,
  isAuthSessionValid,
  ensureAuthenticated
}
