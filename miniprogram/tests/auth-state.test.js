const assert = require('node:assert/strict')
const path = require('node:path')

const projectRoot = path.resolve(__dirname, '..')
const authPath = path.join(projectRoot, 'utils/auth.js')
const requestPath = path.join(projectRoot, 'utils/request.js')
const configPath = path.join(projectRoot, 'utils/config.js')

function resetModules() {
  delete require.cache[authPath]
  delete require.cache[requestPath]
  delete require.cache[configPath]
}

function createWx(initialStorage = {}, requestHandler = null) {
  const storage = { ...initialStorage }
  const calls = { login: 0, request: [] }
  let nextCode = 1

  global.wx = {
    getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
    getStorageSync: key => storage[key],
    setStorageSync: (key, value) => { storage[key] = value },
    removeStorageSync: key => { delete storage[key] },
    getStorageInfoSync: () => ({ keys: Object.keys(storage) }),
    showToast: () => {},
    login: options => {
      calls.login += 1
      options.success({ code: `wx-code-${nextCode++}` })
    },
    request: options => {
      calls.request.push(options)
      if (!requestHandler) throw new Error(`unexpected request: ${options.url}`)
      requestHandler(options, calls)
    }
  }

  return { storage, calls }
}

function authSuccess(options, suffix = '1') {
  options.success({
    statusCode: 200,
    data: {
      access_token: `token-${suffix}`,
      token_type: 'bearer',
      user_id: 'internal-only',
      expires_in: 604800,
      auth_mode: 'fixed_miniprogram',
      is_new_user: false
    }
  })
}

async function testStorageMigrationPreservesDrafts() {
  resetModules()
  const { storage } = createWx({
    token: 'empty-user-token',
    userInfo: { userId: 'empty-user' },
    user_id: 'empty-user',
    authMode: 'legacy',
    auth_mode: 'legacy',
    authStorageVersion: 1,
    lastRefreshTime: 123,
    trendsLastRefresh: 123,
    nutritionLastRefresh: 123,
    nutritionNeedsRefresh: true,
    aiLastRefresh: 123,
    settingsLastRefresh: 123,
    'mealPoster:old': { url: 'expired' },
    pendingMealDraftImage: 'wxfile://do-not-delete'
  })

  const auth = require(authPath)
  assert.equal(auth.migrateAuthStorage(), true)
  assert.equal(storage.authStorageVersion, 2)
  assert.equal(storage.pendingMealDraftImage, 'wxfile://do-not-delete')
  ;[
    'token', 'userInfo', 'user_id', 'authMode', 'auth_mode',
    'lastRefreshTime', 'trendsLastRefresh', 'nutritionLastRefresh',
    'nutritionNeedsRefresh', 'aiLastRefresh', 'settingsLastRefresh',
    'mealPoster:old'
  ].forEach(key => assert.equal(storage[key], undefined, `${key} should be cleared`))
}

async function testConcurrentSilentLoginUsesOnePromise() {
  resetModules()
  const { storage, calls } = createWx({ authStorageVersion: 2 }, options => {
    assert.deepEqual(Object.keys(options.data), ['code'])
    assert.match(options.url, /\/api\/v1\/auth\/miniprogram-login$/)
    setTimeout(() => authSuccess(options), 5)
  })

  const auth = require(authPath)
  const sessions = await Promise.all(Array.from({ length: 6 }, () => auth.ensureAuthenticated()))
  assert.equal(calls.login, 1)
  assert.equal(calls.request.length, 1)
  assert.equal(sessions.every(item => item.authMode === 'fixed_miniprogram'), true)
  assert.equal(storage.authSessionV2.access_token, 'token-1')
  assert.equal(storage.authSessionV2.auth_mode, 'fixed_miniprogram')

  await auth.ensureAuthenticated()
  assert.equal(calls.login, 1, 'valid session should be reused')
}

async function testInvalidCodeRetriesOnlyOnce() {
  resetModules()
  const { calls } = createWx({ authStorageVersion: 2 }, (options, state) => {
    if (state.request.length === 1) {
      options.success({ statusCode: 401, data: { detail: 'invalid code' }, header: {} })
      return
    }
    authSuccess(options, 'retry')
  })

  const auth = require(authPath)
  await auth.ensureAuthenticated()
  assert.equal(calls.login, 2)
  assert.equal(calls.request.length, 2)
}

async function testForbiddenDoesNotRetry() {
  resetModules()
  const { calls } = createWx({ authStorageVersion: 2 }, options => {
    options.success({ statusCode: 403, data: { detail: 'forbidden' }, header: {} })
  })

  const auth = require(authPath)
  await assert.rejects(auth.ensureAuthenticated(), error => {
    assert.equal(error.code, 403)
    assert.equal(error.message, '当前微信账号未获授权')
    return true
  })
  assert.equal(calls.login, 1)
  assert.equal(calls.request.length, 1)
}

async function testConcurrent401UsesOneRefreshAndReplaysOnce() {
  resetModules()
  const now = Date.now()
  const { calls } = createWx({
    authStorageVersion: 2,
    authSessionV2: {
      access_token: 'old-token',
      expires_in: 604800,
      auth_mode: 'fixed_miniprogram',
      login_at: now,
      expires_at: now + 604800000
    }
  }, options => {
    if (options.url.endsWith('/api/v1/auth/miniprogram-login')) {
      setTimeout(() => authSuccess(options, 'refreshed'), 5)
      return
    }

    if (options.header.Authorization === 'Bearer old-token') {
      const delay = options.url.endsWith('/second') ? 12 : 0
      setTimeout(() => options.success({ statusCode: 401, data: {}, header: {} }), delay)
      return
    }

    assert.equal(options.header.Authorization, 'Bearer token-refreshed')
    options.success({ statusCode: 200, data: { ok: true } })
  })

  global.getApp = () => ({ globalData: {}, applyAuthSession: () => {} })
  const { request } = require(requestPath)
  const result = await Promise.all([
    request({ url: '/api/v1/test/first' }),
    request({ url: '/api/v1/test/second' })
  ])

  assert.deepEqual(result, [{ ok: true }, { ok: true }])
  assert.equal(calls.login, 1, 'concurrent 401 responses must share one wx.login')
  assert.equal(calls.request.filter(item => item.url.endsWith('/miniprogram-login')).length, 1)
  assert.equal(calls.request.filter(item => item.url.includes('/api/v1/test/')).length, 4)
}

async function testSecond401Stops() {
  resetModules()
  const now = Date.now()
  const { calls } = createWx({
    authStorageVersion: 2,
    authSessionV2: {
      access_token: 'old-token',
      expires_in: 604800,
      auth_mode: 'fixed_miniprogram',
      login_at: now,
      expires_at: now + 604800000
    }
  }, options => {
    if (options.url.endsWith('/api/v1/auth/miniprogram-login')) {
      authSuccess(options, 'still-invalid')
      return
    }
    options.success({ statusCode: 401, data: {}, header: {} })
  })

  let authFailureNotifications = 0
  global.getApp = () => ({
    globalData: {},
    applyAuthSession: () => {},
    notifyAuthFailure: () => { authFailureNotifications += 1 }
  })
  const { request } = require(requestPath)
  await assert.rejects(request({ url: '/api/v1/test/reject' }), error => {
    assert.equal(error.code, 401)
    assert.equal(error.message, '登录状态异常，请稍后重试')
    return true
  })
  assert.equal(calls.login, 1)
  assert.equal(calls.request.filter(item => item.url.endsWith('/api/v1/test/reject')).length, 2)
  assert.equal(authFailureNotifications, 1, 'terminal 401 should surface the page auth recovery state')
}

async function run() {
  await testStorageMigrationPreservesDrafts()
  await testConcurrentSilentLoginUsesOnePromise()
  await testInvalidCodeRetriesOnlyOnce()
  await testForbiddenDoesNotRetry()
  await testConcurrent401UsesOneRefreshAndReplaysOnce()
  await testSecond401Stops()
  console.log('auth-state tests: ok')
}

run().catch(error => {
  console.error(error)
  process.exitCode = 1
})
