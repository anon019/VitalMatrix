import { useEffect, useState } from 'react'
import { ai } from '@/services/api'
import type { AIRecommendation } from '@/types'

function todayHK() {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: 'Asia/Hong_Kong', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date())
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

function AdviceCard({ title, emoji, items, tone }: { title: string; emoji: string; items: string[]; tone: 'review' | 'action' }) {
  return (
    <section className="card p-5">
      <div className="flex items-center gap-2"><span aria-hidden>{emoji}</span><h3 className="text-[16px] font-semibold">{title}</h3></div>
      <ol className="mt-4 space-y-3">
        {items.map((item, index) => (
          <li key={`${title}-${index}`} className="flex gap-3 text-[14px] leading-6 text-[#3a3a3c]">
            <span className={`mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${tone === 'action' ? 'bg-[#1f684b] text-white' : 'bg-[#eeeef2] text-[#555]'}`}>{index + 1}</span>
            <span>{item}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

export default function AI() {
  const [recommendation, setRecommendation] = useState<AIRecommendation | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [chatReply, setChatReply] = useState<string | null>(null)
  const [chatting, setChatting] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      setRecommendation(await ai.getToday())
    } catch {
      setError('AI 建议加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const regenerate = async () => {
    setGenerating(true)
    setError(null)
    try {
      setRecommendation(await ai.regenerate(todayHK()))
    } catch {
      setError('建议生成失败或请求过于频繁，请稍后重试')
    } finally {
      setGenerating(false)
    }
  }

  const ask = async (event: React.FormEvent) => {
    event.preventDefault()
    const content = question.trim()
    if (!content) return
    setChatting(true)
    setError(null)
    try {
      const response = await ai.chat([{ role: 'user', content }])
      setChatReply(response.message)
    } catch {
      setError('AI 对话失败，请稍后重试')
    } finally {
      setChatting(false)
    }
  }

  if (loading) return <div className="py-24 text-center text-[#86868b]">正在读取今日建议...</div>

  const completeness = recommendation?.generation_metadata?.data_completeness

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="text-[12px] font-semibold tracking-[0.16em] text-[#5e5ce6]">CONTEXT-AWARE COACH</p><h2 className="mt-1 text-[28px] font-semibold tracking-tight">AI 健康建议</h2><p className="mt-1 text-[14px] text-[#86868b]">优先级：饮食 → 睡眠与恢复 → 活动与训练</p></div>
        <button onClick={() => void regenerate()} disabled={generating} className="rounded-full bg-[#1d1d1f] px-4 py-2.5 text-[13px] font-medium text-white disabled:opacity-50">{generating ? 'Codex 正在生成…' : recommendation ? '重新生成今日建议' : '生成今日建议'}</button>
      </div>

      {error && <div className="rounded-xl bg-red-50 px-4 py-3 text-[13px] text-red-700">{error}</div>}

      {recommendation ? (
        <>
          <section className="overflow-hidden rounded-3xl bg-gradient-to-br from-[#e9f7ef] via-white to-[#efefff] p-6 shadow-sm">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-[#666]"><span className="rounded-full bg-white/80 px-2.5 py-1 font-medium text-[#1f684b]">{recommendation.model}</span><span>{recommendation.generation_metadata?.prompt_version ?? '当前提示词'}</span><span>·</span><span>{recommendation.date}</span></div>
            {recommendation.is_stale && <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-[12px] text-amber-800">今日数据尚未生成完整建议，当前显示 {recommendation.source_date} 的最近建议。</div>}
            <p className="mt-5 max-w-3xl text-[24px] font-semibold leading-9 tracking-tight text-[#1d1d1f]">{recommendation.summary}</p>
            {completeness && <div className="mt-5 flex flex-wrap gap-2 text-[11px] text-[#666]"><span className="rounded-full bg-white/70 px-2.5 py-1">饮食记录 {Number(completeness.nutrition_recorded_days ?? 0)} 天</span><span className="rounded-full bg-white/70 px-2.5 py-1">睡眠 {completeness.has_sleep ? '已纳入' : '缺失'}</span><span className="rounded-full bg-white/70 px-2.5 py-1">恢复 {completeness.has_readiness ? '已纳入' : '缺失'}</span><span className="rounded-full bg-white/70 px-2.5 py-1">活动 {completeness.has_activity ? '已纳入' : '缺失'}</span></div>}
          </section>

          <div className="grid gap-4 lg:grid-cols-2"><AdviceCard title={recommendation.yesterday_review.title} emoji={recommendation.yesterday_review.emoji} items={recommendation.yesterday_review.items} tone="review" /><AdviceCard title={recommendation.today_recommendation.title} emoji={recommendation.today_recommendation.emoji} items={recommendation.today_recommendation.items} tone="action" /></div>

          <section className="card p-5"><div className="flex items-center gap-2"><span>{recommendation.health_education.emoji}</span><h3 className="text-[16px] font-semibold">{recommendation.health_education.title}</h3></div><div className="mt-4 grid gap-4 md:grid-cols-2">{recommendation.health_education.sections.map((section, index) => <div key={`${section.subtitle}-${index}`} className="rounded-2xl bg-[#f7f7f9] p-4"><h4 className="text-[14px] font-semibold">{section.subtitle}</h4><dl className="mt-3 space-y-3">{section.items.map((item) => <div key={item.label}><dt className="text-[11px] font-medium text-[#5e5ce6]">{item.label}</dt><dd className="mt-0.5 text-[13px] leading-5 text-[#555]">{item.content}</dd></div>)}</dl></div>)}</div></section>
        </>
      ) : <div className="card py-16 text-center"><p className="text-[14px] text-[#666]">今天还没有 AI 建议。</p><p className="mt-1 text-[12px] text-[#999]">先记录饮食和睡眠，再点击生成会更准确。</p></div>}

      <section className="card p-5"><h3 className="text-[16px] font-semibold">追问 Codex</h3><p className="mt-1 text-[12px] text-[#86868b]">对话会自动带入可信用户画像；客户端补充上下文不能覆盖个人资料。</p><form onSubmit={ask} className="mt-4 flex flex-col gap-3 sm:flex-row"><input value={question} maxLength={4000} onChange={(e) => setQuestion(e.target.value)} placeholder="例如：基于我最近几天吃过的菜，今晚怎么搭配？" className="min-w-0 flex-1 rounded-xl border border-[#d2d2d7] px-4 py-3 text-[14px] outline-none focus:border-[#5e5ce6]" /><button disabled={chatting || !question.trim()} className="rounded-xl bg-[#5e5ce6] px-5 py-3 text-[13px] font-medium text-white disabled:opacity-40">{chatting ? '思考中…' : '发送'}</button></form>{chatReply && <div className="mt-4 whitespace-pre-wrap rounded-2xl bg-[#f6f6fb] p-4 text-[14px] leading-6 text-[#3a3a3c]">{chatReply}</div>}</section>
    </div>
  )
}
