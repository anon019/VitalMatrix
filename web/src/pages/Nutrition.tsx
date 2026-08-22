import { useEffect, useMemo, useState } from 'react'
import { nutrition } from '@/services/api'
import type { MealPosterResponse, MealRecord, WeeklyNutritionTrend } from '@/types'

const mealLabels = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' }

function hkDateTimeInput() {
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Hong_Kong', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(new Date())
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${value.year}-${value.month}-${value.day}T${value.hour}:${value.minute}`
}

function Metric({ label, value, unit }: { label: string; value: number | null; unit: string }) {
  return (
    <div className="rounded-xl bg-[#f5f5f7] px-3 py-2">
      <div className="text-[11px] text-[#86868b]">{label}</div>
      <div className="mt-0.5 text-[17px] font-semibold text-[#1d1d1f]">
        {value == null ? '—' : Math.round(value * 10) / 10}<span className="ml-1 text-[11px] font-normal text-[#86868b]">{unit}</span>
      </div>
    </div>
  )
}

const confidenceLabels = { high: '高置信度', medium: '中等置信度', low: '低置信度' }

function MealImage({ src, alt }: { src: string | null; alt: string }) {
  const [failed, setFailed] = useState(false)

  if (!src || failed) {
    return (
      <div className="flex h-52 w-full flex-col items-center justify-center gap-2 bg-[#f1f1ef] text-[#86868b] md:h-64">
        <span className="text-3xl" aria-hidden="true">🍽️</span>
        <span className="text-[12px]">图片暂时不可用</span>
      </div>
    )
  }

  return (
    <img
      src={src}
      alt={alt}
      className="h-52 w-full object-cover md:h-64"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

function AnalysisDetails({ meal }: { meal: MealRecord }) {
  const analysis = meal.gemini_analysis
  const rating = analysis?.nutrition_analysis
  const quality = analysis?.analysis_quality
  const insights = analysis?.health_insights
  const recommendations = analysis?.recommendations
  const nutritionSummary = analysis?.nutrition_summary
  const plans = recommendations?.next_meal_recipes ?? recommendations?.next_meals ?? []
  const score = rating?.overall_score
  const recommendationsPending = meal.recommendation_status === 'pending' || meal.recommendation_status === 'processing'

  return (
    <div className="space-y-5 border-t border-[#ececf0] bg-[#fcfcfd] p-5">
      <section className="rounded-2xl border border-emerald-100 bg-gradient-to-br from-emerald-50/80 to-white p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold tracking-[0.14em] text-[#2f7d5b]">本餐分析结论</p>
            <h5 className="mt-1 text-[19px] font-semibold text-[#1d1d1f]">{rating?.overall_rating ?? '已完成分析'}</h5>
          </div>
          <div className="flex items-center gap-2">
            {quality?.overall_confidence ? <span className="rounded-full bg-white px-2.5 py-1 text-[11px] text-[#4b6358] shadow-sm">{confidenceLabels[quality.overall_confidence]}</span> : null}
            {score != null ? <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[#1f684b] text-[16px] font-semibold text-white" aria-label={`综合评分 ${score} 分`}>{score}</span> : null}
          </div>
        </div>
        <p className="mt-3 max-w-3xl text-[14px] leading-6 text-[#343438]">{rating?.overall_comment ?? recommendations?.summary ?? '分析结果已保存。'}</p>
        {nutritionSummary?.calorie_range_low != null && nutritionSummary.calorie_range_high != null ? (
          <p className="mt-2 text-[12px] text-[#68716c]">估算区间 {Math.round(nutritionSummary.calorie_range_low)}–{Math.round(nutritionSummary.calorie_range_high)} kcal{nutritionSummary.estimate_note ? ` · ${nutritionSummary.estimate_note}` : ''}</p>
        ) : null}
      </section>

      {(insights?.strengths?.length || insights?.weaknesses?.length) ? (
        <section className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-2xl bg-emerald-50/70 p-4">
            <h6 className="text-[12px] font-semibold text-emerald-800">做得不错</h6>
            <ul className="mt-2 space-y-1.5 text-[13px] leading-5 text-[#425249]">{(insights?.strengths ?? []).slice(0, 3).map((item) => <li key={item}>· {item}</li>)}</ul>
          </div>
          <div className="rounded-2xl bg-amber-50/80 p-4">
            <h6 className="text-[12px] font-semibold text-amber-800">优先调整</h6>
            <ul className="mt-2 space-y-1.5 text-[13px] leading-5 text-[#5d5041]">{(insights?.weaknesses ?? []).slice(0, 3).map((item) => <li key={item}>· {item}</li>)}</ul>
          </div>
        </section>
      ) : null}

      {recommendationsPending ? (
        <section className="rounded-2xl border border-sky-100 bg-sky-50/70 px-4 py-5">
          <div className="flex items-center gap-3">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-sky-500" />
            <div>
              <h5 className="text-[14px] font-semibold text-sky-900">识图已完成，未来三餐正在生成</h5>
              <p className="mt-1 text-[12px] text-sky-700">页面会自动更新，不需要重新上传图片。</p>
            </div>
          </div>
        </section>
      ) : meal.recommendation_status === 'failed' ? (
        <section className="rounded-2xl border border-red-100 bg-red-50/70 px-4 py-4">
          <h5 className="text-[14px] font-semibold text-red-900">未来三餐生成失败</h5>
          <p className="mt-1 text-[12px] text-red-700">{meal.analysis_error || '可以使用餐次卡片上的按钮单独重试，不需要重新上传图片。'}</p>
        </section>
      ) : plans.length ? (
        <section>
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div><p className="text-[11px] font-semibold tracking-[0.14em] text-[#2f7d5b]">NEXT 24 HOURS</p><h5 className="mt-1 text-[17px] font-semibold">未来 24 小时三餐</h5></div>
            <p className="text-[11px] text-[#86868b]">结合近 7 天记录，按时间顺序安排</p>
          </div>
          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            {plans.map((plan, index) => (
              <article key={`${plan.meal_name ?? 'meal'}-${index}`} className="rounded-2xl border border-[#e3e3e8] bg-white p-4 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                <div className="flex items-start justify-between gap-2">
                  <div><span className="text-[11px] font-medium text-[#2f7d5b]">第 {index + 1} 餐</span><h6 className="mt-0.5 text-[15px] font-semibold">{plan.meal_name ?? '正餐'}</h6></div>
                  <div className="text-right text-[11px] text-[#86868b]">{plan.timing}<br />{plan.total_calories != null ? `${Math.round(plan.total_calories)} kcal` : ''}</div>
                </div>
                <div className="mt-3 space-y-3">
                  {(plan.dishes ?? []).map((dish, dishIndex) => (
                    <section key={`${dish.name ?? 'dish'}-${dishIndex}`} className="rounded-xl bg-[#f7f7f8] p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h6 className="text-[13px] font-semibold text-[#343438]">{dish.name}</h6>
                          {dish.portion ? <p className="mt-0.5 text-[11px] text-[#86868b]">建议份量：{dish.portion}</p> : null}
                        </div>
                        <div className="flex gap-1.5 text-[10px] text-[#68716c]">
                          {dish.calories != null ? <span className="rounded-full bg-white px-2 py-1">{Math.round(dish.calories)} kcal</span> : null}
                          {dish.protein != null ? <span className="rounded-full bg-white px-2 py-1">蛋白质 {Math.round(dish.protein * 10) / 10}g</span> : null}
                        </div>
                      </div>
                      {dish.ingredients?.length ? (
                        <div className="mt-3">
                          <p className="text-[10px] font-semibold tracking-[0.1em] text-[#86868b]">食材</p>
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            {dish.ingredients.map((ingredient) => <span key={ingredient} className="rounded-full bg-white px-2 py-1 text-[11px] text-[#555]">{ingredient}</span>)}
                          </div>
                        </div>
                      ) : null}
                      {dish.cooking_steps?.length ? (
                        <div className="mt-3">
                          <p className="text-[10px] font-semibold tracking-[0.1em] text-[#86868b]">做法</p>
                          <ol className="mt-1.5 space-y-1.5">
                            {dish.cooking_steps.map((step, stepIndex) => (
                              <li key={`${stepIndex}-${step}`} className="flex gap-2 text-[11px] leading-5 text-[#555]">
                                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-[10px] font-semibold text-emerald-800">{stepIndex + 1}</span>
                                <span>{step}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      ) : null}
                    </section>
                  ))}
                </div>
                {(plan.flavor_profile || plan.experience_note) ? (
                  <div className="mt-3 space-y-1 text-[11px] leading-5 text-[#65656a]">
                    {plan.flavor_profile ? <p><span className="font-medium text-[#454548]">口味：</span>{plan.flavor_profile}</p> : null}
                    {plan.experience_note ? <p><span className="font-medium text-[#454548]">体验：</span>{plan.experience_note}</p> : null}
                  </div>
                ) : null}
                {plan.why_this_menu ? <p className="mt-3 border-t border-[#efeff2] pt-3 text-[11px] leading-5 text-[#6e6e73]">{plan.why_this_menu}</p> : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {insights?.uncertainty_notes?.length ? <p className="rounded-xl bg-[#f3f3f5] px-3 py-2 text-[11px] leading-5 text-[#6e6e73]">估算说明：{insights.uncertainty_notes.join('；')}</p> : null}
    </div>
  )
}

export default function Nutrition() {
  const [meals, setMeals] = useState<MealRecord[]>([])
  const [weekly, setWeekly] = useState<WeeklyNutritionTrend | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [mealType, setMealType] = useState<MealRecord['meal_type']>('lunch')
  const [mealTime, setMealTime] = useState(hkDateTimeInput)
  const [posterLoadingId, setPosterLoadingId] = useState<string | null>(null)
  const [reanalyzingId, setReanalyzingId] = useState<string | null>(null)
  const [retryingRecommendationId, setRetryingRecommendationId] = useState<string | null>(null)
  const [poster, setPoster] = useState<MealPosterResponse | null>(null)
  const [expandedMealId, setExpandedMealId] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [mealResult, weeklyResult] = await Promise.all([
        nutrition.getMeals(),
        nutrition.getWeekly(),
      ])
      setMeals(mealResult.meals)
      setExpandedMealId((current) => mealResult.meals.some((meal) => meal.id === current) ? current : mealResult.meals[0]?.id ?? null)
      setWeekly(weeklyResult)
    } catch {
      setError('饮食数据加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const pendingRecommendationIds = useMemo(
    () => meals
      .filter((meal) => meal.recommendation_status === 'pending' || meal.recommendation_status === 'processing')
      .map((meal) => meal.id)
      .sort()
      .join(','),
    [meals],
  )

  useEffect(() => {
    if (!pendingRecommendationIds) return

    const mealIds = pendingRecommendationIds.split(',')
    let cancelled = false
    let timer: number | undefined

    const poll = async () => {
      const results = await Promise.all(mealIds.map(async (mealId) => {
        try {
          const status = await nutrition.getAnalysisStatus(mealId)
          if (status.recommendation_status === 'completed') {
            try {
              return { status, meal: await nutrition.getMeal(mealId) }
            } catch {
              return { status, meal: null }
            }
          }
          return { status, meal: null }
        } catch {
          return null
        }
      }))

      if (cancelled) return

      const freshMeals = new Map(
        results.flatMap((result) => result?.meal ? [[result.meal.id, result.meal] as const] : []),
      )
      const statuses = new Map(
        results.flatMap((result) => result ? [[result.status.meal_id, result.status] as const] : []),
      )

      setMeals((current) => current.map((meal) => {
        const freshMeal = freshMeals.get(meal.id)
        if (freshMeal) return freshMeal
        const status = statuses.get(meal.id)
        return status ? {
          ...meal,
          analysis_status: status.analysis_status,
          recommendation_status: status.recommendation_status,
          recommendation_attempts: status.recommendation_attempts,
          analysis_error: status.analysis_error,
          analysis_completed_at: status.analysis_completed_at,
          recommendation_updated_at: status.recommendation_updated_at,
        } : meal
      }))

      const shouldContinue = results.some((result) => (
        !result
        || result.status.recommendation_status === 'pending'
        || result.status.recommendation_status === 'processing'
        || (result.status.recommendation_status === 'completed' && !result.meal)
      ))
      if (shouldContinue && !cancelled) {
        timer = window.setTimeout(() => void poll(), 2500)
      }
    }

    timer = window.setTimeout(() => void poll(), 1200)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [pendingRecommendationIds])

  const previewUrl = useMemo(() => file ? URL.createObjectURL(file) : null, [file])
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  const handleUpload = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('image', file)
      form.append('meal_type', mealType)
      form.append('meal_time', mealTime.replace('T', ' '))
      const uploadedMeal = await nutrition.upload(form)
      setFile(null)
      setMeals((current) => [uploadedMeal, ...current.filter((meal) => meal.id !== uploadedMeal.id)])
      setExpandedMealId(uploadedMeal.id)
      void nutrition.getWeekly().then(setWeekly).catch(() => undefined)
    } catch {
      setError('识图或保存失败，请检查图片后重试')
    } finally {
      setUploading(false)
    }
  }

  const generatePoster = async (mealId: string) => {
    setPosterLoadingId(mealId)
    setError(null)
    try {
      setPoster(await nutrition.generatePoster(mealId))
    } catch {
      setError('海报生成失败或今日额度已用完，请稍后重试')
    } finally {
      setPosterLoadingId(null)
    }
  }

  const reanalyze = async (mealId: string) => {
    setReanalyzingId(mealId)
    setError(null)
    try {
      const updated = await nutrition.reanalyze(mealId)
      setMeals((current) => current.map((meal) => meal.id === mealId ? updated : meal))
    } catch {
      setError('重新分析失败或今日额度已用完，请稍后重试')
    } finally {
      setReanalyzingId(null)
    }
  }

  const retryRecommendations = async (mealId: string) => {
    setRetryingRecommendationId(mealId)
    setError(null)
    try {
      const status = await nutrition.generateRecommendations(mealId)
      setMeals((current) => current.map((meal) => meal.id === mealId ? {
        ...meal,
        analysis_status: status.analysis_status,
        recommendation_status: status.recommendation_status,
        analysis_error: null,
      } : meal))
    } catch {
      setError('饮食建议重新生成失败，请稍后重试')
    } finally {
      setRetryingRecommendationId(null)
    }
  }

  if (loading) return <div className="py-24 text-center text-[#86868b]">正在加载饮食记录...</div>

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[12px] font-semibold tracking-[0.16em] text-[#2f7d5b]">NUTRITION FIRST</p>
        <h2 className="mt-1 text-[28px] font-semibold tracking-tight text-[#1d1d1f]">饮食健康</h2>
        <p className="mt-1 text-[14px] text-[#86868b]">记录真实餐食，让建议结合近 7 天饮食、睡眠与恢复状态。</p>
      </div>

      {error && <div className="rounded-xl bg-red-50 px-4 py-3 text-[13px] text-red-700">{error}</div>}

      <section className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <form onSubmit={handleUpload} className="card p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-[16px] font-semibold">记录一餐</h3>
            <span className="text-[11px] text-[#86868b]">Gemini 3.7 Flash 识图</span>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="sm:row-span-2 flex min-h-44 cursor-pointer items-center justify-center overflow-hidden rounded-2xl border border-dashed border-[#c7c7cc] bg-[#fafafa]">
              {previewUrl ? <img src={previewUrl} alt="待分析餐食" className="h-48 w-full object-cover" /> : <span className="px-6 text-center text-[13px] text-[#86868b]">点击选择餐食照片<br />JPEG / PNG / WebP，最大 10MB</span>}
              <input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </label>
            <select value={mealType} onChange={(e) => setMealType(e.target.value as MealRecord['meal_type'])} className="rounded-xl border border-[#d2d2d7] bg-white px-3 py-3 text-[14px]">
              {Object.entries(mealLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <input type="datetime-local" value={mealTime} onChange={(e) => setMealTime(e.target.value)} className="rounded-xl border border-[#d2d2d7] px-3 py-3 text-[14px]" />
            <button disabled={!file || uploading} className="rounded-xl bg-[#1f684b] px-4 py-3 text-[14px] font-medium text-white transition hover:bg-[#18543d] disabled:cursor-not-allowed disabled:opacity-40">
              {uploading ? '正在识别与分析…' : '分析并保存'}
            </button>
          </div>
        </form>

        <div className="card p-5">
          <p className="text-[12px] text-[#86868b]">近 7 天记录完整度</p>
          <div className="mt-2 flex items-end gap-2"><span className="text-[42px] font-semibold tracking-tight">{weekly?.recorded_days ?? 0}</span><span className="pb-2 text-[14px] text-[#86868b]">/ 7 天</span></div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#e8e8ed]"><div className="h-full rounded-full bg-[#30a46c]" style={{ width: `${((weekly?.recorded_days ?? 0) / 7) * 100}%` }} /></div>
          <div className="mt-5 grid grid-cols-2 gap-3">
            <Metric label="记录日均热量" value={weekly?.weekly_avg_calories ?? null} unit="kcal" />
            <Metric label="记录日均蛋白质" value={weekly?.weekly_avg_protein ?? null} unit="g" />
          </div>
          <p className="mt-4 text-[12px] leading-5 text-[#86868b]">均值只基于有记录的日期；少记一餐不会被误判为全天摄入不足。</p>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between"><h3 className="text-[17px] font-semibold">最近餐食</h3><span className="text-[12px] text-[#86868b]">共 {meals.length} 条</span></div>
        {meals.length === 0 ? (
          <div className="card py-16 text-center text-[14px] text-[#86868b]">上传第一张餐食照片，开始建立饮食上下文。</div>
        ) : meals.map((meal) => {
          const expanded = expandedMealId === meal.id
          return (
            <article key={meal.id} className="card overflow-hidden">
              <div className="grid md:grid-cols-[220px_1fr]">
                <MealImage key={meal.photo_path || meal.id} src={meal.photo_path} alt={`${mealLabels[meal.meal_type]}餐食`} />
                <div className="p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-[18px] font-semibold">{mealLabels[meal.meal_type]}</h4>
                        {meal.analysis_is_legacy ? <span className="rounded-full bg-amber-50 px-2 py-1 text-[11px] text-amber-700">旧版分析</span> : <span className="rounded-full bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">最新分析</span>}
                        {(meal.recommendation_status === 'pending' || meal.recommendation_status === 'processing') ? <span className="rounded-full bg-sky-50 px-2 py-1 text-[11px] text-sky-700">建议生成中</span> : null}
                        {meal.recommendation_status === 'failed' ? <span className="rounded-full bg-red-50 px-2 py-1 text-[11px] text-red-700">建议生成失败</span> : null}
                      </div>
                      <p className="mt-1 text-[12px] text-[#86868b]">{new Date(meal.meal_time).toLocaleString('zh-CN', { timeZone: 'Asia/Hong_Kong' })} · {meal.ai_model}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {meal.analysis_is_legacy ? <button onClick={() => void reanalyze(meal.id)} disabled={reanalyzingId === meal.id} className="rounded-full border border-[#d2d2d7] px-3 py-2 text-[12px] text-[#555] disabled:opacity-50">{reanalyzingId === meal.id ? '正在重新分析…' : '用最新模型重做'}</button> : null}
                      {meal.recommendation_status === 'failed' ? <button onClick={() => void retryRecommendations(meal.id)} disabled={retryingRecommendationId === meal.id} className="rounded-full border border-sky-600 px-3 py-2 text-[12px] font-medium text-sky-700 disabled:opacity-50">{retryingRecommendationId === meal.id ? '正在启动…' : '重新生成建议'}</button> : null}
                      <button onClick={() => setExpandedMealId(expanded ? null : meal.id)} className="rounded-full bg-[#f2f2f4] px-3 py-2 text-[12px] text-[#454548]">{expanded ? '收起详情' : '查看分析'}</button>
                      <button onClick={() => void generatePoster(meal.id)} disabled={posterLoadingId === meal.id} className="rounded-full border border-[#1f684b] px-3 py-2 text-[12px] font-medium text-[#1f684b] hover:bg-emerald-50 disabled:opacity-50">{posterLoadingId === meal.id ? 'Nano Banana 创作中…' : '生成分享海报'}</button>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4"><Metric label="热量" value={meal.total_calories} unit="kcal" /><Metric label="蛋白质" value={meal.total_protein} unit="g" /><Metric label="碳水" value={meal.total_carbs} unit="g" /><Metric label="脂肪" value={meal.total_fat} unit="g" /></div>
                  <div className="mt-4 flex flex-wrap gap-2">{meal.food_items.map((item) => <span key={item.id} className="rounded-full bg-[#f5f5f7] px-2.5 py-1 text-[11px] text-[#666]">{item.food_name}{item.estimated_weight ? ` ${Math.round(item.estimated_weight)}g` : ''}</span>)}</div>
                </div>
              </div>
              {expanded ? <AnalysisDetails meal={meal} /> : null}
            </article>
          )
        })}
      </section>

      {poster && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/65 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="分享海报">
          <div className="mx-auto my-4 max-w-xl rounded-3xl bg-white p-4 shadow-2xl sm:p-6">
            <div className="mb-4 flex items-center justify-between"><div><h3 className="text-[17px] font-semibold">分享海报</h3><p className="text-[11px] text-[#86868b]">{poster.generated ? '本次新生成' : '已复用相同内容'} · {poster.layout_version}</p></div><button onClick={() => setPoster(null)} className="rounded-full bg-[#f0f0f2] px-3 py-2 text-[13px]">关闭</button></div>
            <img src={poster.poster_url} alt="饮食健康分享海报" className="mx-auto h-auto w-full max-w-md rounded-2xl bg-[#eee]" />
            <a href={poster.poster_url} download className="mt-4 block w-full rounded-xl bg-[#1f684b] py-3 text-center text-[14px] font-medium text-white">打开原图 / 保存</a>
            <p className="mt-3 text-center text-[11px] text-[#86868b]">餐食画面由 Nano Banana 2 创作；标题、营养数字和餐单文字均由系统核验排版。</p>
          </div>
        </div>
      )}
    </div>
  )
}
