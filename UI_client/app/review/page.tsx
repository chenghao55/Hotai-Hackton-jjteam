'use client';

import Link from 'next/link';
import { useCallback, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronRight,
  CircleDot,
  Clock3,
  Filter,
  Image as ImageIcon,
  MapPin,
  PanelLeftClose,
  ShieldCheck,
  Sparkles,
  SprayCan,
  Wrench,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  initialCases,
  type CaseStatus,
  type ReviewCase,
  type RiskLevel,
} from '@/lib/prototype';
import { useCaseStatusTool } from '@/hooks/use-webmcp';

type RiskFilter = 'all' | RiskLevel;

const riskMeta: Record<RiskLevel, { label: string; className: string }> = {
  high: { label: '高風險', className: 'border-red-200 bg-red-50 text-red-700' },
  medium: { label: '中風險', className: 'border-amber-200 bg-amber-50 text-amber-700' },
  low: { label: '低風險', className: 'border-emerald-200 bg-emerald-50 text-emerald-700' },
};

const validStatuses: CaseStatus[] = ['待人工覆核', '待清潔', '待維修', '已結案'];

export default function ReviewPage() {
  const [cases, setCases] = useState<ReviewCase[]>(initialCases);
  const [filter, setFilter] = useState<RiskFilter>('all');
  const [selectedId, setSelectedId] = useState(initialCases[0].case_id);
  const [notice, setNotice] = useState('');

  const filtered = useMemo(() => filter === 'all' ? cases : cases.filter((item) => item.risk_level === filter), [cases, filter]);
  const selected = cases.find((item) => item.case_id === selectedId) ?? cases[0];

  const updateStatus = useCallback((caseId: string, rawStatus: string) => {
    if (!validStatuses.includes(rawStatus as CaseStatus) || !cases.some((item) => item.case_id === caseId)) return false;
    const status = rawStatus as CaseStatus;
    setCases((current) => current.map((item) => item.case_id === caseId ? { ...item, status } : item));
    setNotice(`${caseId} 已更新為「${status}」`);
    return true;
  }, [cases]);

  useCaseStatusTool(updateStatus);

  const queueCount = cases.filter((item) => item.status !== '已結案').length;
  const highCount = cases.filter((item) => item.risk_level === 'high' && item.status !== '已結案').length;

  return (
    <main className="min-h-screen bg-[#edf2ee] text-[#14251f]">
      <header className="border-b border-white/10 bg-[#101d1a] text-white">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-5 py-4 lg:px-8">
          <div className="flex items-center gap-3">
            <Link href="/" aria-label="回到首頁" className="grid size-8 place-items-center rounded-lg text-white transition hover:bg-white/10"><ArrowLeft className="size-4" /></Link>
            <span className="grid size-10 place-items-center rounded-xl bg-[#c9ff38] text-[#101d1a]"><ShieldCheck className="size-5" /></span>
            <div><p className="font-semibold">車況案件中心</p><p className="text-xs text-white/55">營運覆核端</p></div>
          </div>
          <div className="flex items-center gap-3">
            <Badge className="hidden border-white/15 bg-white/10 text-white sm:inline-flex">Mock API</Badge>
            <span className="grid size-9 place-items-center rounded-full bg-[#2f4d44] text-sm font-semibold">營</span>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1500px] px-4 py-5 lg:px-8 lg:py-7">
        <section className="mb-5 grid gap-3 sm:grid-cols-3">
          <Metric label="待處理案件" value={queueCount.toString()} note="包含覆核與派工" />
          <Metric label="高風險案件" value={highCount.toString()} note="建議優先處理" accent />
          <Metric label="AI 自動放行" value="72%" note="Prototype 效益假設" />
        </section>

        {notice && <output className="mb-4 flex w-full items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"><span className="flex items-center gap-2"><Check className="size-4" />{notice}</span><button onClick={() => setNotice('')} aria-label="關閉通知"><X className="size-4" /></button></output>}

        <section className="grid min-h-[680px] overflow-hidden rounded-[24px] border bg-white shadow-sm lg:grid-cols-[390px_minmax(0,1fr)]">
          <aside className="border-b lg:border-b-0 lg:border-r">
            <div className="border-b p-4">
              <div className="flex items-center justify-between">
                <h1 className="text-lg font-semibold">案件佇列</h1>
                <span className="text-sm text-muted-foreground">{filtered.length} 件</span>
              </div>
              <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
                {(['all', 'high', 'medium', 'low'] as RiskFilter[]).map((value) => (
                  <button key={value} onClick={() => setFilter(value)} className={`shrink-0 rounded-full border px-3 py-1.5 text-sm font-medium transition ${filter === value ? 'border-[#173e35] bg-[#173e35] text-white' : 'bg-white hover:border-[#6d8b82]'}`}>
                    {value === 'all' ? '全部' : riskMeta[value].label}
                  </button>
                ))}
              </div>
            </div>
            <div className="max-h-[410px] overflow-y-auto lg:max-h-[610px]">
              {filtered.length === 0 ? (
                <div className="grid min-h-56 place-items-center px-8 text-center text-sm text-muted-foreground"><div><Filter className="mx-auto mb-3 size-7" /><p>目前沒有符合條件的案件</p></div></div>
              ) : filtered.map((item) => (
                <button key={item.case_id} onClick={() => setSelectedId(item.case_id)} className={`block w-full border-b p-4 text-left transition hover:bg-[#f7faf7] ${selected.case_id === item.case_id ? 'border-l-4 border-l-[#8bb51c] bg-[#f3f8e9]' : 'border-l-4 border-l-transparent'}`}>
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-semibold">{item.vehicle}</span>
                    <Badge variant="outline" className={riskMeta[item.risk_level].className}>{riskMeta[item.risk_level].label}</Badge>
                  </div>
                  <p className="mt-2 line-clamp-1 text-sm font-medium">{item.summary}</p>
                  <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground"><span>{item.case_id}</span><span>·</span><span>{item.submittedAt}</span></div>
                </button>
              ))}
            </div>
          </aside>

          <CaseDetail item={selected} onUpdate={updateStatus} />
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value, note, accent = false }: { label: string; value: string; note: string; accent?: boolean }) {
  return <div className={`rounded-2xl border p-4 ${accent ? 'border-[#d9ef9b] bg-[#eaffaa]' : 'bg-white'}`}><p className="text-sm text-muted-foreground">{label}</p><div className="mt-1 flex items-end justify-between gap-3"><strong className="text-3xl tracking-tight">{value}</strong><span className="text-xs text-muted-foreground">{note}</span></div></div>;
}

function CaseDetail({ item, onUpdate }: { item: ReviewCase; onUpdate: (id: string, status: string) => boolean }) {
  return (
    <article className="min-w-0 p-5 lg:p-7">
      <div className="flex flex-col justify-between gap-4 border-b pb-5 sm:flex-row sm:items-start">
        <div>
          <div className="flex flex-wrap items-center gap-2"><h2 className="text-2xl font-semibold">{item.vehicle}</h2><Badge variant="outline" className={riskMeta[item.risk_level].className}>{riskMeta[item.risk_level].label}</Badge><Badge variant="secondary">{item.status}</Badge></div>
          <div className="mt-3 flex flex-wrap gap-4 text-sm text-muted-foreground"><span className="flex items-center gap-1.5"><MapPin className="size-4" />{item.location}</span><span className="flex items-center gap-1.5"><Clock3 className="size-4" />{item.submittedAt}</span></div>
        </div>
        <span className="text-sm text-muted-foreground">案件 {item.case_id}</span>
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.1fr_.9fr]">
        <section>
          <div className="mb-3 flex items-center justify-between"><h3 className="font-semibold">借還車影像比較</h3><span className="text-xs text-muted-foreground">同角度對位</span></div>
          <div className="grid grid-cols-2 gap-3">
            <PhotoPlaceholder label="借車前" />
            <PhotoPlaceholder label="還車後" damaged={item.vehicle_change.detected} dirty={item.cleanliness.level === 'dirty'} />
          </div>
          {item.vehicle_change.detected && <div className="mt-3 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm leading-6 text-red-800"><AlertTriangle className="mt-1 size-4 shrink-0" />紅色區域為差異候選，不代表已確認車損或責任。</div>}
        </section>

        <section className="rounded-2xl border bg-[#f8faf8] p-5">
          <div className="flex items-center justify-between"><h3 className="flex items-center gap-2 font-semibold"><Sparkles className="size-4 text-[#5c8610]" />AI 判讀</h3><span className="text-sm font-semibold">{Math.round(item.confidence * 100)}%</span></div>
          <Progress value={item.confidence * 100} className="mt-3 h-2 [&>div]:bg-[#7aa419]" />
          <p className="mt-1 text-xs text-muted-foreground">模型信心分數，不等同案件正確率</p>

          <dl className="mt-5 space-y-4 text-sm">
            <ResultLine label="拍攝品質" value={item.capture_quality.passed ? '通過' : '需補拍'} ok={item.capture_quality.passed} />
            <ResultLine label="新增車損" value={item.vehicle_change.detected ? '疑似有變化' : '未發現'} ok={!item.vehicle_change.detected} />
            <ResultLine label="車內整潔" value={item.cleanliness.level === 'dirty' ? '髒污' : item.cleanliness.level === 'clean' ? '乾淨' : '普通'} ok={item.cleanliness.level !== 'dirty'} />
          </dl>
          <div className="mt-5 rounded-xl bg-white p-3 text-sm leading-6 text-muted-foreground"><strong className="text-foreground">觀察摘要：</strong>{item.vehicle_change.findings[0] ?? item.cleanliness.findings[0] ?? item.summary}</div>
        </section>
      </div>

      <section className="mt-6 rounded-2xl border p-5">
        <div className="flex items-center justify-between"><div><h3 className="font-semibold">人工覆核與下一步</h3><p className="mt-1 text-sm text-muted-foreground">AI 提供優先序，最終處置由營運人員確認。</p></div><PanelLeftClose className="hidden size-5 text-muted-foreground sm:block" /></div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <ActionButton icon={<Check />} label="確認無異常" onClick={() => onUpdate(item.case_id, '已結案')} />
          <ActionButton icon={<CircleDot />} label="保留待覆核" onClick={() => onUpdate(item.case_id, '待人工覆核')} />
          <ActionButton icon={<SprayCan />} label="建立清潔任務" onClick={() => onUpdate(item.case_id, '待清潔')} />
          <ActionButton icon={<Wrench />} label="建立維修任務" onClick={() => onUpdate(item.case_id, '待維修')} />
        </div>
      </section>
    </article>
  );
}

function PhotoPlaceholder({ label, damaged = false, dirty = false }: { label: string; damaged?: boolean; dirty?: boolean }) {
  return (
    <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-[linear-gradient(145deg,#dfe7e2,#aabbb3)]">
      <div className="absolute inset-x-[17%] bottom-[18%] h-[34%] rounded-[45%_35%_20%_20%] border-2 border-white/60 bg-[#526861]/35 shadow-xl" />
      <div className="absolute inset-x-[30%] bottom-[45%] h-[20%] rounded-t-[45%] border-2 border-b-0 border-white/55 bg-[#80938c]/45" />
      {damaged && <span className="absolute bottom-[27%] right-[16%] size-12 rounded-full border-2 border-red-500 bg-red-500/25 shadow-[0_0_0_10px_rgb(239_68_68/12%)]" />}
      {dirty && <span className="absolute bottom-[20%] left-[35%] h-8 w-16 rounded-full border-2 border-amber-500 bg-amber-500/25" />}
      <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-black/55 px-2.5 py-1 text-xs text-white backdrop-blur"><ImageIcon className="size-3" />{label}</span>
    </div>
  );
}

function ResultLine({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return <div className="flex items-center justify-between"><dt className="text-muted-foreground">{label}</dt><dd className={`font-medium ${ok ? 'text-emerald-700' : 'text-amber-700'}`}>{value}</dd></div>;
}

function ActionButton({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return <Button variant="outline" className="h-auto justify-between py-3 text-left hover:border-[#86a91e] hover:bg-[#f3f8e9]" onClick={onClick}><span className="flex items-center gap-2">{icon}{label}</span><ChevronRight className="size-4 text-muted-foreground" /></Button>;
}
