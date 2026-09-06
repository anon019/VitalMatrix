const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

function pageWith(api = {}) {
  let definition
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,
    '../pages/nutrition-detail/nutrition-detail.js'), 'utf8'), {
    Page: value => { definition = value },
    require: () => ({ resolveApiUrl: value => value || '', clearCache() {}, ...api }),
    console: { warn() {}, error() {} }, setTimeout, clearTimeout,
  })
  return Object.assign(definition, {
    data: { ...definition.data, mealId: 'test-meal', recommendationStatus: 'processing' },
    _isActive: true, _isVisible: true,
    _recommendationPollStartedAt: Date.now(),
    setData(update, callback) { Object.assign(this.data, update); callback?.() },
  })
}

test('detail reads score and recommendations from ai_analysis', () => {
  const page = pageWith()
  page.applyMealData({
    id: 'test-meal', meal_type: 'breakfast', meal_time: '2026-09-06T08:00:00+08:00',
    recommendation_status: 'completed',
    ai_analysis: {
      nutrition_analysis: { overall_score: 68, overall_rating: '一般' },
      recommendations: { summary: 'Test recommendation', next_meal_recipes: [] },
    },
  })
  assert.equal(page.data.analysis.nutrition_analysis.overall_score, 68)
  assert.equal(page.data.analysis.recommendations.summary, 'Test recommendation')
})

test('completed status retries when detail refresh fails', async () => {
  const page = pageWith({ getMealAnalysisStatus: async () => ({ recommendation_status: 'completed' }) })
  page.loadMealDetail = async () => false
  let scheduled = 0
  page.scheduleRecommendationPoll = () => scheduled++
  await page.pollRecommendationStatus()
  assert.equal(page.data.recommendationStatus, 'processing')
  assert.equal(scheduled, 1)
  assert.equal(page._recommendationPollPromise, null)
})

test('completed detail ends polling without scheduling another request', async () => {
  const page = pageWith({ getMealAnalysisStatus: async () => ({ recommendation_status: 'completed' }) })
  page.loadMealDetail = async () => true
  page.scheduleRecommendationPoll = () => assert.fail('Should not schedule after successful refresh')
  await page.pollRecommendationStatus()
  assert.equal(page._recommendationPollPromise, null)
})
