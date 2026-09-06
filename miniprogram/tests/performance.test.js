const assert = require('node:assert/strict')
const authPath = require.resolve('../utils/auth.js')
require.cache[authPath] = {
  id: authPath, filename: authPath, loaded: true,
  exports: { ensureAuthenticated: async () => ({}), getAccessToken: () => 'test' }
}
const calls = []
const storage = {}
global.wx = {
  getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
  getStorageSync: key => storage[key],
  setStorageSync: (key, value) => { storage[key] = value },
  showToast: () => {},
  request: options => calls.push(options)
}
global.getApp = () => ({ globalData: {} })
const api = require('../utils/request.js')
const tick = () => new Promise(resolve => setImmediate(resolve))
const respond = (call, data) => call.success({ statusCode: 200, data })

async function testCacheConcurrency() {
  api.clearAllCache()
  const first = api.get('/test/shared')
  const second = api.get('/test/shared')
  await tick()
  assert.equal(calls.length, 1, 'cold concurrent GETs share one request')
  respond(calls[0], { version: 1 })
  assert.deepEqual(await Promise.all([first, second]), [{ version: 1 }, { version: 1 }])
  await api.get('/test/shared')
  assert.equal(calls.length, 1, 'settled GET is cached')

  const stale = api.get('/test/shared', {}, true, true)
  await tick()
  api.clearCache('/test/shared')
  const fresh = api.get('/test/shared')
  await tick()
  respond(calls[2], { version: 3 })
  await fresh
  respond(calls[1], { version: 2 })
  await stale
  assert.deepEqual(await api.get('/test/shared'), { version: 3 }, 'invalidated late response cannot overwrite fresh cache')

  const a = api.get('/test/params', { a: '1&b=2' })
  const b = api.get('/test/params', { a: '1', b: '2' })
  await tick()
  assert.equal(calls.length, 5, 'query values must not collide with parameter separators')
  respond(calls[3], 'a')
  respond(calls[4], 'b')
  assert.deepEqual(await Promise.all([a, b]), ['a', 'b'])
}

function createPage() {
  let definition
  global.Page = value => { definition = value }
  delete require.cache[require.resolve('../pages/nutrition/nutrition.js')]
  require('../pages/nutrition/nutrition.js')
  return {
    ...definition, _isActive: true, _mealListRevision: 1,
    data: { ...definition.data, meals: [{ id: 'one' }], pageSize: 2 },
    patches: [],
    setData(patch) {
      this.patches.push(patch)
      for (const [key, value] of Object.entries(patch)) {
        const match = key.match(/^meals\[(\d+)\]$/)
        if (match) this.data.meals[Number(match[1])] = value
        else this.data[key] = value
      }
    }
  }
}

async function testPagination() {
  const page = createPage()
  const count = calls.length
  const first = page.loadMoreMeals()
  const duplicate = page.loadMoreMeals()
  assert.equal(first, duplicate)
  await tick()
  assert.equal(calls.length, count + 1)
  respond(calls[count], { meals: [{ id: 'one' }, { id: 'two' }, { id: 'two' }], total: 8 })
  await first
  assert.deepEqual(page.data.meals.map(meal => meal.id), ['one', 'two'])
  assert.ok(page.patches.some(patch => patch['meals[1]']))
  assert.equal(page.patches.some(patch => patch.meals), false, 'pagination only serializes appended rows')
  assert.equal(page.data.loadingMore, false)

  const oldPage = page.loadMoreMeals()
  await tick()
  const refresh = page.loadRecentMeals()
  await tick()
  respond(calls[count + 2], { meals: [{ id: 'fresh' }], total: 1 })
  await refresh
  respond(calls[count + 1], { meals: [{ id: 'stale' }], total: 8 })
  await oldPage
  assert.deepEqual(page.data.meals.map(meal => meal.id), ['fresh'])
  assert.equal(page.data.currentPage, 1)
  assert.equal(page.data.hasMore, false)

  const unloaded = createPage()
  const work = unloaded.loadMoreMeals()
  await tick()
  unloaded._isActive = false
  const patches = unloaded.patches.length
  respond(calls[calls.length - 1], { meals: [{ id: 'late' }], total: 5 })
  await work
  assert.equal(unloaded.patches.length, patches, 'unloaded pages receive no setData')
}

async function testRefreshFailure() {
  const page = createPage()
  storage.nutritionLastRefresh = 123
  page._hasLoadedOnce = true
  const refresh = page.loadData({ silent: true })
  await tick()
  const pending = calls.slice(-3)
  pending.forEach(call => call.fail({ errMsg: 'network offline' }))
  await refresh
  assert.deepEqual(page.data.meals, [{ id: 'one' }], 'failed refresh preserves last successful view')
  assert.equal(storage.nutritionLastRefresh, 123, 'failure is never marked fresh')
  assert.match(page.data.loadError, /重试/)
  assert.equal(page._loadPromise, null)
  assert.equal(page.formatMealItem({ total_protein: '12.5' }).total_protein, '12.5')
}

async function testAiViewPayload() {
  let page
  global.Page = definition => { page = definition }
  require('../pages/ai/ai.js')
  page._isActive = true
  page.data = { ...page.data }
  page.setData = patch => Object.assign(page.data, patch)
  const normalize = page.buildRecommendationView
  let conversions = 0
  page.buildRecommendationView = function (data) {
    conversions++
    return normalize.call(this, data)
  }
  const work = page.performLoadData({ silent: true })
  await tick()
  respond(calls[calls.length - 1], {
    summary: '今日建议', model: 'response-model',
    today_recommendation: { unused: 'large payload' }
  })
  await work
  assert.equal(conversions, 1)
  assert.equal(page.data.summary, '今日建议')
  assert.equal(page.data.aiModel, 'response-model')
  assert.equal(page.data.todayRecommendation, undefined)
}

async function main() {
  await testCacheConcurrency()
  await testPagination()
  await testRefreshFailure()
  await testAiViewPayload()
  console.log('performance tests: ok')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
