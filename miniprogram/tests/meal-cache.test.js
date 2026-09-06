const assert = require('node:assert/strict')
const authPath = require.resolve('../utils/auth.js')
const storage = { nutritionLastRefresh: 123, 'mealPoster:old': {}, imageDraft: 'keep', authSession: 'keep' }
let clears = 0
require.cache[authPath] = {
  id: authPath, filename: authPath, loaded: true,
  exports: {
    ensureAuthenticated: async () => ({ accessToken: 'test' }),
    getAccessToken: () => 'test',
    migrateAuthStorage: () => false,
    clearPersistentBusinessCache: () => {
      clears++
      delete storage.nutritionLastRefresh
      delete storage['mealPoster:old']
    }
  }
}
let requests = 0
global.wx = {
  getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
  getStorageSync: key => storage[key],
  setStorageSync: (key, value) => { storage[key] = value },
  request: options => {
    requests++
    options.success({ statusCode: 200, data: { revision: requests } })
  }
}
global.getApp = () => ({ globalData: {} })
async function main() {
  const api = require('../utils/request.js')
  await api.get('/api/v1/nutrition/meals', {})
  const first = await api.getMeals({}, false)
  const second = await api.getMeals({}, false)
  assert.notEqual(first.revision, second.revision)
  await api.get('/api/v1/nutrition/meals/test', {})
  const detail1 = await api.getMealDetail('test', false)
  const detail2 = await api.getMealDetail('test', false)
  assert.notEqual(detail1.revision, detail2.revision)
  assert.equal(requests, 6)
  let app
  global.App = definition => { app = definition }
  require('../app.js')
  app.initializeAuthentication = async () => ({})
  app.onLaunch()
  app.onLaunch()
  assert.equal(clears, 1)
  assert.equal(storage.mealAnalysisSchemaVersion, 1)
  assert.equal(storage.nutritionLastRefresh, undefined)
  assert.equal(storage.imageDraft, 'keep')
  assert.equal(storage.authSession, 'keep')
  console.log('meal-cache tests: ok')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
