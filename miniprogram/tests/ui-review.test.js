const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const projectRoot = path.resolve(__dirname, '..')

global.wx = {
  getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
  getStorageSync: () => null,
  removeStorageSync: () => {},
  setStorageSync: () => {},
  getStorageInfoSync: () => ({ keys: [] })
}
global.getApp = () => ({ globalData: {} })

function loadPageDefinition(relativePath) {
  let definition = null
  global.Page = value => { definition = value }
  const absolutePath = path.join(projectRoot, relativePath)
  delete require.cache[absolutePath]
  require(absolutePath)
  return definition
}

function createPage(definition) {
  return {
    ...definition,
    data: JSON.parse(JSON.stringify(definition.data)),
    setData(patch, callback) {
      Object.assign(this.data, patch)
      if (callback) callback()
    }
  }
}

function testNutritionTrendUsesStableScale() {
  const definition = loadPageDefinition('pages/trends/trends.js')
  const page = createPage(definition)
  page.getLast7Days = () => [
    '2026-08-19', '2026-08-20', '2026-08-21', '2026-08-22',
    '2026-08-23', '2026-08-24', '2026-08-25'
  ]

  const cards = page.buildNutritionTrendCards({
    calories: [1200, 1400, 1600, 1800, 2000, 395, 1882],
    protein_g: [40, 50, 60, 70, 80, 11.3, 87],
    carbs_g: [150, 180, 200, 220, 240, 60.1, 260],
    fat_g: [40, 50, 60, 70, 80, 12.7, 90],
    meals_count: [3, 3, 3, 3, 3, 1, 5]
  })

  const calories = cards.find(card => card.field === 'calories')
  const protein = cards.find(card => card.field === 'protein_g')
  const carbs = cards.find(card => card.field === 'carbs_g')
  const fat = cards.find(card => card.field === 'fat_g')
  const meals = cards.find(card => card.field === 'meals_count')

  assert.equal(calories.scaleMax, 2000)
  assert.equal(calories.values[5].percent, 20)
  assert.equal(calories.values[6].percent, 94)
  assert.equal(protein.scaleMax, 100)
  assert.equal(carbs.scaleMax, 300)
  assert.equal(fat.scaleMax, 100)
  assert.equal(meals.scaleMax, 6)
  assert.match(calories.scaleLabel, /统一刻度 0–2000kcal/)
}

function testHealthInsightsRenderCompletelyAndViewPayloadIsPruned() {
  const definition = loadPageDefinition('pages/nutrition-detail/nutrition-detail.js')
  const page = createPage(definition)
  page._isActive = true
  page._isVisible = true
  page._mealMediaUnavailable = false

  page.applyMealData({
    id: 'meal-1',
    meal_type: 'dinner',
    meal_time: '2026-08-25T19:00:00+08:00',
    total_calories: 680,
    total_protein: 42,
    total_carbs: 78,
    total_fat: 21,
    recommendation_status: 'completed',
    health_insights: {
      strengths: ['优点一', '优点二', '优点三'],
      weaknesses: ['改进一', '改进二', '改进三'],
      risk_factors: ['风险一']
    },
    recommendations: {
      summary: '未来 24 小时建议',
      action_items: ['补充蔬菜'],
      next_meal_recipes: [{ meal_name: '早餐', dishes: [] }]
    },
    ai_analysis: {
      unused_large_payload: { should_not_enter_view: true }
    }
  })

  assert.deepEqual(page.data.strengths, ['优点一', '优点二', '优点三'])
  assert.deepEqual(page.data.weaknesses, ['改进一', '改进二', '改进三'])
  assert.equal(page.toggleInsights, undefined)
  assert.equal(page.data.meal.ai_analysis, undefined)
  assert.equal(page.data.analysis.unused_large_payload, undefined)
  assert.equal(page.data.analysis.recommendations.next_meal_recipes, undefined)
  assert.equal(page.data.nextMealRecipes.length, 1)

  const wxml = fs.readFileSync(path.join(projectRoot, 'pages/nutrition-detail/nutrition-detail.wxml'), 'utf8')
  const wxss = fs.readFileSync(path.join(projectRoot, 'pages/nutrition-detail/nutrition-detail.wxss'), 'utf8')
  assert.doesNotMatch(wxml, /展开|收起|toggleInsights|insight-toggle/)
  assert.doesNotMatch(wxss, /insight-toggle/)
}

function testNutritionListItemsOnlyContainRenderedFields() {
  const definition = loadPageDefinition('pages/nutrition/nutrition.js')
  const page = createPage(definition)
  page._unavailableMealImages = new Set()

  const item = page.formatMealItem({
    id: 'meal-2',
    meal_type: 'lunch',
    meal_time: '2026-08-25T12:30:00+08:00',
    total_calories: 520,
    total_protein: 31,
    total_carbs: 62,
    total_fat: 18,
    thumbnail_path: '/media/meal-2-thumb.jpg',
    nutrition_analysis: { overall_rating: '良好', overall_score: 82 },
    recommendations: { next_meal_recipes: [{ large: 'payload' }] },
    ai_analysis: { large: 'payload' }
  })

  assert.deepEqual(Object.keys(item).sort(), [
    'id', 'image_unavailable', 'meal_time_formatted', 'meal_type_label',
    'overall_rating', 'overall_score', 'ratingColorClass', 'thumbnail_path',
    'total_calories', 'total_carbs', 'total_fat', 'total_protein'
  ])
  assert.equal(item.ai_analysis, undefined)
  assert.equal(item.recommendations, undefined)
}

function testChartMarkupHasNoFullHeightTracks() {
  const wxml = fs.readFileSync(path.join(projectRoot, 'pages/trends/trends.wxml'), 'utf8')
  const wxss = fs.readFileSync(path.join(projectRoot, 'pages/trends/trends.wxss'), 'utf8')
  assert.doesNotMatch(wxml, /柱高按本指标 7 日峰值/)
  assert.doesNotMatch(wxml, /nutrition-bar-track/)
  assert.doesNotMatch(wxss, /\.nutrition-bar-track/)
  assert.match(wxml, /nutrition-bar-column/)
}

function testTodayDynamicStylesUsePrecomputedViewFields() {
  const wxml = fs.readFileSync(path.join(projectRoot, 'pages/index/index.wxml'), 'utf8')
  const dynamicStyles = [...wxml.matchAll(/style="([^"]*\{\{[^"]*)"/g)]
    .map(match => match[1])

  assert.ok(dynamicStyles.length > 0)
  dynamicStyles.forEach(style => {
    assert.match(style, /^\{\{[\w.]+\}\}$/)
    assert.doesNotMatch(style, /\|\||\?|\+|width:|left:|--progress:/)
  })
}

function testAiAnalysisContract() {
  const page = createPage(loadPageDefinition('pages/nutrition-detail/nutrition-detail.js'))
  page._isActive = true
  page._isVisible = true
  const recipes = ['早餐', '午餐', '晚餐'].map((name, index) => ({
    meal_name: name, timing: `${index + 7}:00`, total_calories: 400 + index,
    dishes: [{ name: '蔬菜饭', calories: 400, ingredients: ['米饭', '蔬菜'] }],
    why_this_menu: '补充膳食纤维'
  }))
  const meal = {
    id: 'new-analysis', current_ai_model: 'server-selected-model',
    recommendation_status: 'completed',
    photo_path: 'https://example.com/photo.jpg?signature=abc&expires=123',
    nutrition_analysis: {}, identified_foods: [], recommendations: {}, next_meal_recipes: [],
    ai_analysis: {
      nutrition_analysis: { overall_score: 68, overall_rating: '良好' },
      identified_foods: Array.from({ length: 5 }, (_, i) => ({ name: `食物${i}` })),
      recommendations: { next_meal_recipes: recipes }
    }
  }
  page.applyMealData(meal)
  assert.equal(page.data.nutritionAnalysis.overall_score, 68)
  assert.equal(page.data.analysis.identified_foods.length, 5)
  assert.equal(page.data.currentAiModel, 'server-selected-model')
  assert.equal(page.data.meal.photo_path, meal.photo_path)
  assert.equal(page.data.nextMealRecipes.length, 3)
  page.data.nextMealRecipes.forEach((recipe, index) => {
    for (const key of ['meal_name', 'timing', 'total_calories', 'why_this_menu']) {
      assert.equal(recipe[key], recipes[index][key])
    }
    assert.equal(recipe.dishes[0].name, '蔬菜饭')
  })
  const list = createPage(loadPageDefinition('pages/nutrition/nutrition.js'))
  assert.equal(list.formatMealItem(meal).overall_score, 68)
  list._isActive = true
  list.data.meals = [{ id: 'older' }, { id: meal.id }]
  wx.navigateTo = () => {}
  list.openUploadedMeal(meal)
  assert.deepEqual(list.data.meals.map(item => item.id), [meal.id, 'older'])
}

testAiAnalysisContract()
testNutritionTrendUsesStableScale()
testHealthInsightsRenderCompletelyAndViewPayloadIsPruned()
testNutritionListItemsOnlyContainRenderedFields()
testChartMarkupHasNoFullHeightTracks()
testTodayDynamicStylesUsePrecomputedViewFields()
console.log('ui-review tests: ok')
