const {
  getMealDetail,
  getMealAnalysisStatus,
  requestMealRecommendations,
  deleteMeal,
  generateMealPoster,
  resolveApiUrl,
  clearCache
} = require('../../utils/request.js')

const RECOMMENDATION_POLL_INTERVAL = 2000
const RECOMMENDATION_POLL_TIMEOUT = 90000

const MEAL_TYPE_LABELS = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐'
}

Page({
  data: {
    loading: true,
    loadError: '',
    mealId: '',
    meal: null,
    imageLoadFailed: false,
    analysis: null,
    nutritionAnalysis: null,
    currentAiModel: '',
    mealTypeLabel: '',
    mealTimeFormatted: '',
    calorieRangeText: '',
    overallConclusion: '',
    confidenceLabel: '未提供',
    confidenceClass: 'confidence-unknown',
    portionAssumption: '',
    uncertaintyNotes: [],
    strengths: [],
    weaknesses: [],
    riskFactors: [],
    showAnalysisDetails: false,
    showRecipeDetails: false,
    nextMealRecipes: [],
    nextMealTips: [],
    activeRecipeIndex: 0,
    analysisStatus: 'completed',
    recommendationStatus: '',
    analysisError: '',
    showRecommendationSection: false,
    hasRecommendationContent: false,
    recommendationPolling: false,
    recommendationTimedOut: false,
    retryingRecommendations: false,
    posterGenerationBlocked: true,
    ratingBadgeColor: '#64748B',
    ratingScoreColor: '#64748B',
    carbsRatingClass: 'rating-neutral',
    proteinRatingClass: 'rating-neutral',
    fatRatingClass: 'rating-neutral',
    generatingPoster: false,
    savingPoster: false,
    showPosterPreview: false,
    posterUrl: '',
    posterDisplayUrl: '',
    posterRenderKey: '',
    posterImageLoading: false,
    posterImageError: '',
    posterDigest: '',
    posterModel: '',
    posterLayoutVersion: '',
    posterVerifiedMetrics: null,
    posterAriaLabel: '营养分享海报',
    posterGenerated: false,
    posterError: '',
    posterWaitingHidden: false
  },

  onLoad(options) {
    this._isActive = true
    this._isVisible = true
    this._mealMediaUnavailable = false
    this._posterFailedUrl = ''
    const mealId = options.mealId || ''
    if (!mealId) {
      this.setData({ loading: false, loadError: '没有找到这条饮食记录' })
      return
    }

    this.setData({ mealId })
    wx.removeStorageSync(`mealPoster:${mealId}`)

    const app = getApp()
    this._mealMediaUnavailable = Boolean(app.globalData.unavailableMealImages?.[String(mealId)])
    const pendingMeals = app.globalData.pendingMealRecords || {}
    const pendingMeal = pendingMeals[String(mealId)]
    if (pendingMeal) {
      delete pendingMeals[String(mealId)]
      this.applyMealData(pendingMeal)
      this.loadMealDetail({ silent: true })
    } else {
      this.loadMealDetail()
    }
  },

  onShow() {
    this._isVisible = true
    if (['pending', 'processing'].includes(this.data.recommendationStatus) && !this.data.recommendationTimedOut) {
      this.startRecommendationPolling()
    }
  },

  onHide() {
    this._isVisible = false
    this.clearRecommendationPolling()
  },

  onUnload() {
    this._isActive = false
    this._isVisible = false
    this.clearRecommendationPolling()
  },

  loadMealDetail(options = {}) {
    if (this._detailPromise) return this._detailPromise

    const detailPromise = this.performLoadMealDetail(options).finally(() => {
      if (this._detailPromise === detailPromise) this._detailPromise = null
    })
    this._detailPromise = detailPromise
    return detailPromise
  },

  async performLoadMealDetail({ force = false, silent = false } = {}) {
    const showLoading = !silent && !this.data.meal
    if (showLoading) this.setData({ loading: true, loadError: '' })
    if (force) clearCache(`/api/v1/nutrition/meals/${this.data.mealId}`)

    try {
      const meal = await getMealDetail(this.data.mealId, force)
      this.applyMealData(meal)
      return true
    } catch (error) {
      console.error('加载餐食详情失败:', error)
      if (!this._isActive) return
      if (showLoading || !this.data.meal) {
        this.setData({
          loading: false,
          loadError: error.message || '网络开了小差，请稍后重试'
        })
      }
      return false
    }
  },

  applyMealData(meal = {}) {
    if (!this._isActive) return

    const rawAnalysis = meal.ai_analysis || meal.analysis || {}
    const nutritionAnalysis = rawAnalysis.nutrition_analysis || meal.nutrition_analysis || null
    const nutritionSummary = rawAnalysis.nutrition_summary || {}
    const quality = rawAnalysis.analysis_quality || meal.analysis_quality || {}
    const insights = rawAnalysis.health_insights || meal.health_insights || {}
    const identifiedFoods = Array.isArray(rawAnalysis.identified_foods)
      ? rawAnalysis.identified_foods
      : (Array.isArray(meal.identified_foods) ? meal.identified_foods : [])
    const recommendationCandidate = rawAnalysis.recommendations || meal.recommendations
    const rawRecommendations = recommendationCandidate && typeof recommendationCandidate === 'object' && !Array.isArray(recommendationCandidate)
      ? recommendationCandidate
      : {}
    const recipeSource = rawRecommendations.next_meal_recipes ?? rawAnalysis.next_meal_recipes ?? meal.next_meal_recipes
    const tipSource = meal.next_meal_tips ?? rawAnalysis.next_meal_tips ?? rawRecommendations.next_meal_tips
    const actionItems = Array.isArray(rawRecommendations.action_items)
      ? rawRecommendations.action_items.map(item => typeof item === 'string'
        ? { action: item, rationale: '', priority: 'normal' }
        : item).filter(Boolean)
      : []
    const recommendations = {
      ...rawRecommendations,
      summary: rawRecommendations.summary || meal.recommendation_summary || '',
      action_items: actionItems,
      next_meal_recipes: Array.isArray(recipeSource) ? recipeSource : [],
      next_meal_tips: Array.isArray(tipSource) ? tipSource : []
    }
    const recommendationView = this.processNextMealRecipes(recommendations)
    // 只把模板实际使用的字段传入视图层，避免把完整模型响应和菜谱数组
    // 重复序列化到 meal、analysis 与 nextMealRecipes 三份数据中。
    const analysis = {
      nutrition_analysis: nutritionAnalysis,
      identified_foods: identifiedFoods,
      recommendations: {
        summary: recommendations.summary,
        action_items: recommendations.action_items,
        hydration_reminder: recommendations.hydration_reminder || ''
      }
    }
    const confidence = this.formatConfidence(quality.overall_confidence)
    const strengths = Array.isArray(insights.strengths) ? insights.strengths : []
    const weaknesses = Array.isArray(insights.weaknesses) ? insights.weaknesses : []
    const uncertaintyNotesSource = meal.uncertainty_notes || insights.uncertainty_notes || quality.uncertainty_notes
    const uncertaintyNotes = Array.isArray(uncertaintyNotesSource) ? uncertaintyNotesSource : []
    const hasRecommendationContent = Boolean(
      recommendations.summary
      || recommendations.action_items.length
      || recommendations.next_meal_recipes.length
      || recommendations.next_meal_tips.length
      || recommendations.hydration_reminder
    )
    const hasRecommendationStatus = typeof meal.recommendation_status === 'string' && meal.recommendation_status.length > 0
    const recommendationStatus = hasRecommendationStatus
      ? meal.recommendation_status.toLowerCase()
      : (recommendations.next_meal_recipes.length ? 'completed' : '')
    const analysisStatus = String(meal.analysis_status || 'completed').toLowerCase()
    const photoPath = resolveApiUrl(meal.photo_path)
    const imageLoadFailed = Boolean(this._mealMediaUnavailable)
    const posterUrl = resolveApiUrl(meal.poster_url)
    const posterDigest = meal.content_digest || rawAnalysis.content_digest || ''
    const posterLayoutVersion = meal.poster_layout_version || meal.layout_version || ''
    const posterVerifiedMetrics = meal.verified_metrics || null
    const calorieSource = {
      calorie_range_low: meal.calorie_range_low ?? rawAnalysis.calorie_range_low ?? nutritionSummary.calorie_range_low,
      calorie_range_high: meal.calorie_range_high ?? rawAnalysis.calorie_range_high ?? nutritionSummary.calorie_range_high
    }

    this.setData({
      meal: {
        id: meal.id,
        meal_type: meal.meal_type,
        meal_time: meal.meal_time,
        notes: meal.notes || '',
        total_calories: Math.round(Number(meal.total_calories) || 0),
        total_protein: this.formatNutrient(meal.total_protein),
        total_carbs: this.formatNutrient(meal.total_carbs),
        total_fat: this.formatNutrient(meal.total_fat),
        total_fiber: this.formatNutrient(meal.total_fiber),
        photo_path: photoPath,
        thumbnail_path: resolveApiUrl(meal.thumbnail_path)
      },
      imageLoadFailed,
      analysis,
      nutritionAnalysis,
      currentAiModel: meal.current_ai_model || '',
      mealTypeLabel: MEAL_TYPE_LABELS[meal.meal_type] || meal.meal_type || '餐食',
      mealTimeFormatted: this.formatMealTime(meal.meal_time),
      calorieRangeText: this.formatCalorieRange(calorieSource, meal.total_calories),
      overallConclusion: this.formatOverallConclusion(
        meal.overall_conclusion || nutritionAnalysis?.overall_comment,
        rawAnalysis.overall_conclusion
      ),
      confidenceLabel: confidence.label,
      confidenceClass: confidence.className,
      portionAssumption: String(quality.portion_assumption || ''),
      uncertaintyNotes,
      strengths,
      weaknesses,
      riskFactors: Array.isArray(insights.risk_factors) ? insights.risk_factors : [],
      showAnalysisDetails: false,
      showRecipeDetails: false,
      nextMealRecipes: recommendationView.nextMealRecipes,
      nextMealTips: recommendationView.nextMealTips,
      activeRecipeIndex: 0,
      analysisStatus,
      recommendationStatus,
      posterGenerationBlocked: recommendationStatus !== 'completed',
      analysisError: meal.analysis_error || '',
      showRecommendationSection: hasRecommendationStatus || hasRecommendationContent,
      hasRecommendationContent,
      recommendationTimedOut: false,
      ratingBadgeColor: this.getRatingColor(nutritionAnalysis?.overall_rating),
      ratingScoreColor: this.getRatingColor(nutritionAnalysis?.overall_rating),
      carbsRatingClass: this.getNutritionRatingClass(nutritionAnalysis?.carbs_analysis?.rating),
      proteinRatingClass: this.getNutritionRatingClass(nutritionAnalysis?.protein_analysis?.rating),
      fatRatingClass: this.getNutritionRatingClass(nutritionAnalysis?.fat_analysis?.rating),
      posterUrl,
      posterDisplayUrl: '',
      posterRenderKey: '',
      posterImageLoading: false,
      posterImageError: '',
      posterDigest,
      posterModel: '',
      posterLayoutVersion,
      posterVerifiedMetrics,
      posterAriaLabel: this.formatPosterAriaLabel(posterVerifiedMetrics),
      posterGenerated: false,
      posterError: '',
      loading: false,
      loadError: ''
    }, () => this.syncRecommendationPolling(recommendationStatus))
  },

  retryLoad() {
    this.loadMealDetail({ force: true })
  },

  syncRecommendationPolling(status) {
    if (['pending', 'processing'].includes(status)) {
      this.startRecommendationPolling()
    } else {
      this.clearRecommendationPolling()
    }
  },

  startRecommendationPolling({ reset = false } = {}) {
    if (!this._isActive || !this._isVisible || !this.data.mealId) return
    if (reset || !this._recommendationPollStartedAt) this._recommendationPollStartedAt = Date.now()
    if (this._recommendationPollTimer || this._recommendationPollPromise) return
    this.setData({ recommendationPolling: true, recommendationTimedOut: false })
    this.scheduleRecommendationPoll()
  },

  scheduleRecommendationPoll(delay = RECOMMENDATION_POLL_INTERVAL) {
    if (!this._isActive || !this._isVisible) return
    clearTimeout(this._recommendationPollTimer)
    this._recommendationPollTimer = setTimeout(() => {
      this._recommendationPollTimer = null
      this.pollRecommendationStatus()
    }, delay)
  },

  async pollRecommendationStatus() {
    if (!this._isActive || !this._isVisible || this._recommendationPollPromise) return
    if (Date.now() - this._recommendationPollStartedAt >= RECOMMENDATION_POLL_TIMEOUT) {
      this.clearRecommendationPolling({ preserveStart: true })
      this.setData({ recommendationTimedOut: true, recommendationPolling: false })
      return
    }

    const pollPromise = getMealAnalysisStatus(this.data.mealId)
    this._recommendationPollPromise = pollPromise
    try {
      const status = await pollPromise
      if (!this._isActive || !this._isVisible) return
      const recommendationStatus = String(status?.recommendation_status || 'pending').toLowerCase()
      if (recommendationStatus === 'completed') {
        // 详情成功刷新后再展示完成；暂时失败继续轮询，保留原有超时上限。
        if (this._detailPromise) await this._detailPromise
        if (!this._isActive || !this._isVisible) return
        const loaded = await this.loadMealDetail({ force: true, silent: true })
        if (loaded) return
        if (this._isActive && this._isVisible) this.scheduleRecommendationPoll()
        return
      }
      this.setData({
        analysisStatus: status?.analysis_status || this.data.analysisStatus,
        recommendationStatus,
        posterGenerationBlocked: recommendationStatus !== 'completed',
        analysisError: status?.analysis_error || ''
      })

      if (recommendationStatus === 'failed') {
        this.clearRecommendationPolling()
        return
      }
    } catch (error) {
      console.warn('查询饮食建议状态失败:', error)
    } finally {
      if (this._recommendationPollPromise === pollPromise) this._recommendationPollPromise = null
    }

    if (this._isActive && this._isVisible && ['pending', 'processing'].includes(this.data.recommendationStatus)) {
      this.scheduleRecommendationPoll()
    }
  },

  clearRecommendationPolling({ preserveStart = false } = {}) {
    if (this._recommendationPollTimer) clearTimeout(this._recommendationPollTimer)
    this._recommendationPollTimer = null
    if (!preserveStart) this._recommendationPollStartedAt = null
    if (this._isActive && this.data.recommendationPolling) {
      this.setData({ recommendationPolling: false })
    }
  },

  retryRecommendations() {
    return this.requestRecommendations(false)
  },

  requestRecommendations(force = false) {
    if (this._recommendationRetryPromise || !this.data.mealId) return this._recommendationRetryPromise
    this.clearRecommendationPolling()
    this.setData({
      retryingRecommendations: true,
      recommendationStatus: 'processing',
      posterGenerationBlocked: true,
      showRecommendationSection: true,
      recommendationTimedOut: false,
      analysisError: ''
    })

    const requestPromise = requestMealRecommendations(this.data.mealId, force)
      .then(() => {
        if (!this._isActive) return
        this.setData({ retryingRecommendations: false })
        this.startRecommendationPolling({ reset: true })
      })
      .catch(error => {
        console.error('重新生成饮食建议失败:', error)
        if (!this._isActive) return
        this.setData({
          retryingRecommendations: false,
          recommendationStatus: 'failed',
          posterGenerationBlocked: true,
          analysisError: error.message || '饮食建议生成请求失败'
        })
      })
      .finally(() => {
        if (this._recommendationRetryPromise === requestPromise) this._recommendationRetryPromise = null
      })

    this._recommendationRetryPromise = requestPromise
    return requestPromise
  },

  confirmRegenerateRecommendations() {
    if (this.data.retryingRecommendations) return
    wx.showModal({
      title: '重新生成未来 24 小时建议？',
      content: '系统会结合近期饮食重新生成建议，不会重新上传或识别图片。',
      confirmText: '重新生成',
      confirmColor: '#27624F',
      success: result => {
        if (result.confirm) this.requestRecommendations(true)
      }
    })
  },

  formatNutrient(value) {
    return (Number(value) || 0).toFixed(1)
  },

  formatMealTime(value) {
    if (!value) return ''
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return ''
    const month = date.getMonth() + 1
    const day = date.getDate()
    const hour = String(date.getHours()).padStart(2, '0')
    const minute = String(date.getMinutes()).padStart(2, '0')
    return `${month}月${day}日 ${hour}:${minute}`
  },

  formatCalorieRange(summary, fallbackCalories) {
    const low = Number(summary.calorie_range_low)
    const high = Number(summary.calorie_range_high)
    if (low > 0 && high >= low) return `${Math.round(low)}–${Math.round(high)}`
    return String(Math.round(Number(fallbackCalories) || 0))
  },

  formatConfidence(value) {
    const normalized = String(value || '').toLowerCase()
    const map = {
      high: { label: '高置信度', className: 'confidence-high' },
      medium: { label: '中等置信度', className: 'confidence-medium' },
      low: { label: '低置信度', className: 'confidence-low' }
    }
    return map[normalized] || { label: '未提供', className: 'confidence-unknown' }
  },

  getRatingColor(rating) {
    const colors = {
      '优秀': '#15803D',
      '良好': '#2563EB',
      '一般': '#D97706',
      '需改善': '#D97706',
      '较差': '#DC2626'
    }
    return colors[rating] || '#64748B'
  },

  getNutritionRatingClass(rating) {
    if (['适量', '适中', '合理', '正常', '充足', '均衡'].includes(rating)) return 'rating-good'
    if (['偏高', '偏低', '过甜', '过咸', '过量', '稍高', '稍低'].includes(rating)) return 'rating-warning'
    if (['严重偏高', '严重不足', '严重过量', '过高', '过低'].includes(rating)) return 'rating-danger'
    return 'rating-neutral'
  },

  formatOverallConclusion(primary, fallback) {
    const value = String(primary || fallback || '').replace(/\s+/g, ' ').trim()
    if (!value) return ''
    const firstSentence = (value.match(/^.*?[。！？!?]/) || [value])[0]
    return firstSentence && firstSentence.length >= 18 ? firstSentence : value
  },

  formatListText(value, separator = '、') {
    if (!Array.isArray(value)) return String(value || '')
    return value.map(item => {
      if (typeof item === 'string') return item
      if (!item || typeof item !== 'object') return ''
      return [item.amount || item.quantity || item.weight, item.name || item.ingredient || item.step || item.description]
        .filter(Boolean)
        .join(' ')
    }).filter(Boolean).join(separator)
  },

  normalizeIngredientItems(value) {
    const source = Array.isArray(value)
      ? value
      : (value && typeof value === 'object'
          ? [value]
          : String(value || '').split(/[\n、，,；;]+/))

    return source.map(item => {
      if (typeof item === 'string') return { text: item.trim() }
      if (!item || typeof item !== 'object') return null
      const name = item.name || item.ingredient || item.material || item.description || item.text || ''
      const amount = item.amount ?? item.quantity ?? item.weight ?? item.portion ?? ''
      return { text: [name, amount].filter(part => part !== '').join(' ').trim() }
    }).filter(item => item && item.text)
  },

  normalizeCookingSteps(value) {
    const rawSource = Array.isArray(value) ? value : [value]
    const source = []
    rawSource.forEach(item => {
      if (typeof item !== 'string') {
        if (item) source.push(item)
        return
      }
      const rawText = item.replace(/\r/g, '').trim()
      if (!rawText) return
      const withoutStepNumbers = rawText.replace(/(^|\s)\d{1,2}[.、）)]\s*/g, '$1\n')
      withoutStepNumbers
        .split(/\n+|\s*(?:→|->|；|;)\s*/)
        .filter(Boolean)
        .forEach(step => source.push(step))
    })

    return source.map(item => {
      if (typeof item === 'string') return { text: item.replace(/^\d{1,2}[.、）)]\s*/, '').trim() }
      if (!item || typeof item !== 'object') return null
      const text = item.step || item.description || item.instruction || item.method || item.text || ''
      return { text: String(text).replace(/^\d{1,2}[.、）)]\s*/, '').trim() }
    }).filter(item => item && item.text)
  },

  normalizeDish(dish = {}) {
    const calories = dish.calories ?? dish.estimated_calories ?? dish.calorie ?? dish.kcal ?? dish.energy_kcal
    const protein = dish.protein ?? dish.protein_g ?? dish.estimated_protein
    const ingredients = dish.ingredients
      ?? dish.ingredient_list
      ?? dish.materials
      ?? dish.ingredient_details
    const cookingSteps = dish.cooking_steps
      ?? dish.steps
      ?? dish.method
      ?? dish.instructions
      ?? dish.directions
      ?? dish.preparation
    const ingredientItems = this.normalizeIngredientItems(ingredients)
    const cookingStepItems = this.normalizeCookingSteps(cookingSteps)
    return {
      name: dish.name || dish.dish_name || '',
      calories: Math.round(Number(calories) || 0),
      portion: this.formatListText(dish.portion ?? dish.serving_size ?? dish.serving),
      protein: Number(protein) || 0,
      cooking_time: dish.cooking_time || dish.prep_time || '',
      ingredients: ingredientItems,
      cooking_steps: cookingStepItems,
      hasRecipeDetails: Boolean(ingredientItems.length || cookingStepItems.length),
      health_benefit: dish.health_benefit || dish.benefit || dish.nutrition_benefit || ''
    }
  },

  formatMealRecipeName(recipe = {}, fallbackIndex = 0) {
    const mealName = String(recipe.meal_name || recipe.meal || '下一餐').trim()
    const matched = mealName.match(/^((?:次日)?(?:早餐|午餐|晚餐|加餐|夜宵)|breakfast|lunch|dinner|snack)\s*[：:]\s*(.+)$/i)
    const rawMealLabel = matched?.[1] || String(recipe.meal_type || recipe.meal || '下一餐')
    const identitySource = [rawMealLabel, recipe.meal_type, recipe.meal, mealName, recipe.timing]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    const fallbackTypes = ['breakfast', 'lunch', 'dinner', 'snack']
    const mealType = /早餐|早饭|breakfast|morning/.test(identitySource)
      ? 'breakfast'
      : /午餐|午饭|lunch|midday/.test(identitySource)
        ? 'lunch'
        : /晚餐|晚饭|dinner|supper|evening/.test(identitySource)
          ? 'dinner'
          : /加餐|夜宵|点心|snack/.test(identitySource)
            ? 'snack'
            : (fallbackTypes[fallbackIndex] || 'snack')
    const presentation = {
      breakfast: { label: '早餐', icon: '🌅', theme: 'breakfast' },
      lunch: { label: '午餐', icon: '☀️', theme: 'lunch' },
      dinner: { label: '晚餐', icon: '🌙', theme: 'dinner' },
      snack: { label: '加餐', icon: '🍎', theme: 'snack' }
    }[mealType]
    const menuTitle = matched?.[2] || mealName
    return {
      mealName,
      mealLabel: presentation.label,
      menuTitle,
      icon: presentation.icon,
      theme: presentation.theme
    }
  },

  normalizeMealRecipe(recipe = {}, fallbackIndex = 0) {
    const dishes = Array.isArray(recipe.dishes) ? recipe.dishes.map(item => this.normalizeDish(item)) : []
    const name = this.formatMealRecipeName(recipe, fallbackIndex)
    return {
      meal_name: name.mealName,
      meal_label: name.mealLabel,
      menu_title: name.menuTitle,
      meal_icon: name.icon,
      meal_theme: name.theme,
      timing: recipe.timing || recipe.recommended_time || '',
      total_calories: Math.round(Number(recipe.total_calories) || dishes.reduce((sum, dish) => sum + dish.calories, 0)),
      dishes,
      dish_count: dishes.length,
      hasDetailedRecipes: dishes.some(dish => dish.hasRecipeDetails),
      flavor_profile: recipe.flavor_profile || '',
      experience_note: recipe.experience_note || '',
      staple: recipe.staple || null,
      why_this_menu: recipe.why_this_menu || recipe.reason || ''
    }
  },

  processNextMealRecipes(recommendations = {}) {
    const recipeSource = Array.isArray(recommendations.next_meal_recipes)
      ? recommendations.next_meal_recipes
      : (recommendations.next_meal_recipe ? [recommendations.next_meal_recipe] : [])
    const tipSource = Array.isArray(recommendations.next_meal_tips) ? recommendations.next_meal_tips : []

    return {
      nextMealRecipes: recipeSource.map((recipe, index) => this.normalizeMealRecipe(recipe, index)),
      nextMealTips: tipSource.map(tip => typeof tip === 'string'
        ? { meal: '饮食提示', suggestion: tip, health_benefit: '' }
        : {
            meal: tip.meal || '下一餐',
            suggestion: tip.suggestion || '',
            health_benefit: tip.health_benefit || ''
          })
    }
  },

  toggleAnalysisDetails() {
    this.setData({ showAnalysisDetails: !this.data.showAnalysisDetails })
  },

  toggleRecipeDetails() {
    this.setData({ showRecipeDetails: !this.data.showRecipeDetails })
  },

  selectMealRecipe(event) {
    const index = Number(event.currentTarget.dataset.index)
    if (!Number.isInteger(index) || index < 0 || index >= this.data.nextMealRecipes.length) return
    this.setData({ activeRecipeIndex: index })
  },

  generatePoster() {
    if (this.data.generatingPoster) return
    if (this.data.posterGenerationBlocked) {
      this.setData({ posterError: '' })
      return
    }
    // 海报地址是短期签名 URL。即使已有 posterUrl，也通过普通接口刷新签名；
    // 服务端缓存命中会返回 generated=false，不会消耗新的生成额度。
    return this.requestPoster(false)
  },

  requestPoster(force, options = {}) {
    if (this._posterPromise) return this._posterPromise
    if (!this.data.meal) return Promise.resolve()

    const { keepPreview = false, propagateError = false } = options
    this.setData({ generatingPoster: true, showPosterPreview: keepPreview, posterError: '', posterWaitingHidden: false })
    const posterPromise = generateMealPoster(this.data.mealId, force)
      .then(result => {
        if (!result?.poster_url) throw new Error('服务端未返回海报地址')
        const posterUrl = resolveApiUrl(result.poster_url)
        if (!this._isActive) return result
        const posterDigest = String(result.content_digest || '')
        const posterRenderKey = posterDigest.replace(/[^a-zA-Z0-9_-]/g, '-') || String(Date.now())
        const posterVerifiedMetrics = result.verified_metrics || null

        // 先卸载旧图片，再挂载接口刚返回的签名地址。这样即使对象路径相同，
        // content_digest 变化后也不会继续显示微信图片组件中的旧内容。
        this.setData({
          generatingPoster: false,
          showPosterPreview: true,
          posterUrl,
          posterDisplayUrl: '',
          posterRenderKey: '',
          posterImageLoading: true,
          posterImageError: '',
          posterDigest,
          posterModel: result.model || '',
          posterLayoutVersion: result.layout_version || '',
          posterVerifiedMetrics,
          posterAriaLabel: this.formatPosterAriaLabel(posterVerifiedMetrics),
          posterGenerated: result.generated === true,
          posterError: ''
        }, () => {
          if (!this._isActive) return
          if (posterUrl !== this._posterFailedUrl) this._posterFailedUrl = ''
          this.setData({
            posterDisplayUrl: posterUrl,
            posterRenderKey
          })
        })
        return result
      })
      .catch(error => {
        console.error('生成海报失败:', error)
        if (!this._isActive) {
          if (propagateError) throw error
          return null
        }
        const posterError = this.formatPosterRequestError(error)
        this.setData({
          generatingPoster: false,
          posterError
        })
        if (propagateError) throw error
        return null
      })
      .finally(() => {
        if (this._posterPromise === posterPromise) this._posterPromise = null
      })

    this._posterPromise = posterPromise
    return posterPromise
  },

  confirmRegeneratePoster() {
    if (this.data.generatingPoster || this.data.posterGenerationBlocked) return
    wx.showModal({
      title: '重新生成海报？',
      content: '这会重新消耗一次 AI 生成额度，并替换当前海报。',
      confirmText: '重新生成',
      confirmColor: '#B45309',
      success: result => {
        if (result.confirm) this.requestPoster(true)
      }
    })
  },

  closePosterPreview() {
    this.setData({ showPosterPreview: false })
  },

  hidePosterWaiting() {
    this.setData({ posterWaitingHidden: true })
    wx.showToast({ title: '仍在后台等待，请勿重复发起', icon: 'none' })
  },

  onPreviewTap() {},

  callWxApi(name, options) {
    return new Promise((resolve, reject) => {
      wx[name]({ ...options, success: resolve, fail: reject })
    })
  },

  formatVerifiedMetrics(metrics) {
    if (!metrics || typeof metrics !== 'object') return ''
    const definitions = [
      [['calories', 'calories_kcal', 'total_calories', 'energy_kcal'], '热量', 'kcal'],
      [['protein_g', 'total_protein'], '蛋白质', 'g'],
      [['carbs_g', 'total_carbs'], '碳水', 'g'],
      [['fat_g', 'total_fat'], '脂肪', 'g']
    ]
    return definitions
      .map(([keys, label, unit]) => {
        const key = keys.find(candidate => metrics[candidate] !== undefined && metrics[candidate] !== null)
        return key ? `${label} ${metrics[key]}${unit}` : ''
      })
      .filter(Boolean)
      .join(' · ')
  },

  formatPosterAriaLabel(metrics) {
    const metricSummary = this.formatVerifiedMetrics(metrics)
    return metricSummary ? `营养分享海报，${metricSummary}` : '营养分享海报'
  },

  formatPosterRequestError(error = {}) {
    if (error.code === 'TIMEOUT') {
      return '生成等待超过 120 秒，请稍后重试；服务端可能仍在处理中'
    }

    const detail = error.data?.detail
    let backendMessage = error.message
    if (Array.isArray(detail)) {
      backendMessage = detail
        .map(item => typeof item === 'string' ? item : item?.msg || item?.message || '')
        .filter(Boolean)
        .join('；')
    } else if (detail && typeof detail === 'object') {
      backendMessage = detail.message || detail.msg || backendMessage
    } else if (typeof detail === 'string') {
      backendMessage = detail
    }

    return String(backendMessage || '海报生成失败，请检查网络后重试')
  },

  async refreshPosterUrl() {
    await this.requestPoster(false, { keepPreview: true, propagateError: true })
    return this.data.posterUrl
  },

  async downloadPosterWithRefresh(hasRetried = false) {
    const download = await this.callWxApi('downloadFile', {
      url: this.data.posterUrl,
      timeout: 120000
    })
    if (download.statusCode === 403 && !hasRetried) {
      await this.refreshPosterUrl()
      return this.downloadPosterWithRefresh(true)
    }
    if (download.statusCode && download.statusCode >= 400) {
      const error = new Error(download.statusCode === 403 ? '海报链接已过期，请重新打开海报' : '海报下载失败')
      error.code = download.statusCode
      throw error
    }
    return download.tempFilePath
  },

  async savePoster() {
    if (this.data.savingPoster || !this.data.posterUrl) return
    this.setData({ savingPoster: true })

    try {
      const filePath = await this.downloadPosterWithRefresh(false)
      const imageInfo = await this.callWxApi('getImageInfo', { src: filePath })
      if (!imageInfo.width || !imageInfo.height) throw new Error('无法读取海报尺寸')
      await this.callWxApi('saveImageToPhotosAlbum', { filePath })
      if (!this._isActive) return
      this.setData({ savingPoster: false })
      wx.showToast({ title: '已保存完整海报', icon: 'success' })
    } catch (error) {
      console.error('保存海报失败:', error)
      if (!this._isActive) return
      this.setData({ savingPoster: false })
      const message = error.errMsg || error.message || ''
      if (/auth|authorize|permission|deny/i.test(message)) {
        this.showAlbumPermissionGuide()
      } else {
        const failureContent = /timeout/i.test(message)
          ? '海报下载超过 120 秒，请稍后重试。'
          : error.code === 403
            ? '海报链接已过期且刷新失败，请重新打开海报。'
            : '没有保存成功，请检查网络后重试。'
        wx.showModal({
          title: '保存失败',
          content: failureContent,
          showCancel: false,
          confirmText: '我知道了'
        })
      }
    }
  },

  showAlbumPermissionGuide() {
    wx.showModal({
      title: '需要相册权限',
      content: '请在设置中允许保存到相册，返回后可再次点击保存。',
      confirmText: '去设置',
      success: result => {
        if (!result.confirm) return
        wx.openSetting({
          success: setting => {
            if (this._isActive && setting.authSetting['scope.writePhotosAlbum']) this.savePoster()
          }
        })
      }
    })
  },

  async performDelete() {
    wx.showLoading({ title: '删除中…', mask: true })
    try {
      await deleteMeal(this.data.mealId)
      clearCache('/api/v1/nutrition')
      wx.setStorageSync('nutritionNeedsRefresh', true)
      wx.hideLoading()
      wx.showToast({ title: '已删除', icon: 'success' })
      setTimeout(() => {
        if (this._isActive) wx.navigateBack()
      }, 1000)
    } catch (error) {
      wx.hideLoading()
      wx.showModal({ title: '删除失败', content: error.message || '请稍后重试', showCancel: false })
    }
  },

  deleteMeal() {
    wx.showModal({
      title: '删除这条记录？',
      content: '删除后无法恢复。',
      confirmText: '删除',
      confirmColor: '#DC2626',
      success: result => {
        if (result.confirm) this.performDelete()
      }
    })
  },

  onImageError() {
    if (this._mealMediaUnavailable) return
    this._mealMediaUnavailable = true
    const app = getApp()
    if (!app.globalData.unavailableMealImages) app.globalData.unavailableMealImages = {}
    app.globalData.unavailableMealImages[String(this.data.mealId)] = true
    this.setData({ imageLoadFailed: true })
  },

  onPosterImageLoad() {
    if (!this._isActive) return
    this.setData({ posterImageLoading: false, posterImageError: '' })
  },

  onPosterImageError() {
    const failedUrl = this.data.posterDisplayUrl
    if (!failedUrl || this._posterFailedUrl === failedUrl || this.data.generatingPoster) return
    this._posterFailedUrl = failedUrl
    this.setData({ posterImageLoading: true, posterImageError: '' })
    this.refreshPosterUrl().catch(() => {
      if (this._isActive) {
        this.setData({
          posterImageLoading: false,
          posterImageError: '海报链接刷新失败，请稍后重试',
          posterError: '海报链接刷新失败，请稍后重试'
        })
      }
    })
  },

  onShareAppMessage() {
    const meal = this.data.meal || {}
    return {
      title: `我的${this.data.mealTypeLabel} · ${meal.total_calories || 0} 千卡`,
      path: `/pages/nutrition-detail/nutrition-detail?mealId=${this.data.mealId}`,
      imageUrl: this.data.posterUrl || meal.photo_path || ''
    }
  }
})
