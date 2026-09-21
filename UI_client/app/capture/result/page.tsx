'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleDollarSign,
  FileSearch,
  Image as ImageIcon,
  LoaderCircle,
  ShieldCheck,
} from 'lucide-react';
import { readCaptureResult, readCaptureThumbnails, type StoredAnalysisResult } from '@/lib/capture-flow';
import type { CompensationEstimate, DamageFinding } from '@/lib/prototype';

export default function CaptureResultPage() {
  const [result, setResult] = useState<StoredAnalysisResult | null>(null);
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [appealSubmitted, setAppealSubmitted] = useState(false);

  useEffect(() => {
    const caseId = new URLSearchParams(window.location.search).get('case_id');
    const stored = readCaptureResult(caseId);
    setResult(stored);
    if (stored) {
      setThumbnails(readCaptureThumbnails(stored.case_id));
      const appealKey = `capture-appeal-submitted:${stored.case_id}`;
      setAppealSubmitted(sessionStorage.getItem(appealKey) === 'true');
      sessionStorage.removeItem(appealKey);
    }
    setLoading(false);
  }, []);

  if (loading) return <ResultLoading />;
  if (!result) return <MissingResult />;
  if (result.recommended_action === 'pass') return <SuccessResult result={result} />;
  return <ReviewResult result={result} thumbnails={thumbnails} appealSubmitted={appealSubmitted} />;
}

function ResultShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><ShieldCheck className="size-5" aria-hidden="true" /></span>
              <div><p className="font-semibold">車況管家</p><p className="mt-0.5 text-sm text-white/55">還車檢查結果</p></div>
            </div>
            <span className="rounded-full border border-white/15 px-3 py-1.5 text-sm text-white/70">車輛 7A21</span>
          </div>
        </header>
        {children}
      </div>
    </main>
  );
}

function ResultLoading() {
  return (
    <ResultShell>
      <div className="grid min-h-[70dvh] place-items-center px-8 text-center" role="status">
        <div><LoaderCircle className="mx-auto size-9 animate-spin text-[#2d6d5d]" /><p className="mt-4 font-semibold">正在整理檢查結果…</p></div>
      </div>
    </ResultShell>
  );
}

function MissingResult() {
  return (
    <ResultShell>
      <section className="grid min-h-[70dvh] place-items-center px-6 py-10 text-center">
        <div>
          <span className="mx-auto grid size-20 place-items-center rounded-full bg-amber-50 text-amber-700"><AlertTriangle className="size-9" /></span>
          <h1 className="mt-5 text-2xl font-semibold">找不到本次分析結果</h1>
          <p className="mt-2 text-base leading-6 text-[#62756d]">結果可能已隨分頁關閉而清除，請返回拍攝流程重新送出分析。</p>
          <Link href="/capture/camera" className="mt-7 inline-flex h-14 w-full items-center justify-center gap-2 rounded-2xl bg-[#173e35] px-5 font-semibold text-white hover:bg-[#22594b]">返回拍攝流程<ArrowRight className="size-5" /></Link>
        </div>
      </section>
    </ResultShell>
  );
}

function SuccessResult({ result }: { result: StoredAnalysisResult }) {
  return (
    <ResultShell>
      <section className="px-5 pb-8 pt-8 sm:px-7">
        <div className="text-center">
          <span className="mx-auto grid size-24 place-items-center rounded-full bg-[#dfff8b] text-[#173e35] shadow-[0_12px_30px_rgb(105_145_21/18%)]"><CheckCircle2 className="size-12" aria-hidden="true" /></span>
          <p className="mt-6 text-sm font-semibold tracking-wide text-[#2d6d5d]">檢查完成</p>
          <h1 className="mt-2 text-[32px] font-semibold leading-tight tracking-tight">還車檢查已完成</h1>
          <p className="mx-auto mt-3 max-w-sm text-base leading-7 text-[#62756d]">未偵測到新增損傷或需收費的清潔問題，本次不需支付額外費用。</p>
        </div>

        <div className="mt-8 rounded-[26px] border border-[#dce9e1] bg-[#f7faf8] p-5">
          <div className="flex items-center justify-between"><h2 className="font-semibold">檢查摘要</h2><span className="rounded-full bg-[#e2f5e8] px-3 py-1 text-sm font-semibold text-[#276a5a]">已結案</span></div>
          <dl className="mt-5 divide-y divide-[#dfe9e3]">
            <SummaryRow label="拍攝照片" value="8 張皆完成" />
            <SummaryRow label="案件編號" value={result.case_id} />
            <SummaryRow label="完成時間" value={formatDate(result.analyzed_at)} />
          </dl>
        </div>

        <div className="mt-5 flex items-start gap-3 rounded-2xl bg-[#eff6f1] p-4 text-sm leading-6 text-[#45645b]">
          <ShieldCheck className="mt-0.5 size-5 shrink-0 text-[#2d6d5d]" />本次影像與檢查結果已完成紀錄，還車流程可以結束。
        </div>
        <Link href="/" className="mt-7 inline-flex h-16 w-full items-center justify-center gap-2 rounded-2xl bg-[#173e35] px-5 text-lg font-semibold text-white shadow-[0_8px_20px_rgb(23_62_53/18%)] hover:bg-[#22594b]">完成並返回首頁<ArrowRight className="size-5" /></Link>
      </section>
    </ResultShell>
  );
}

function ReviewResult({ result, thumbnails, appealSubmitted }: { result: StoredAnalysisResult; thumbnails: Record<string, string>; appealSubmitted: boolean }) {
  const findings = normalizeFindings(result);
  const estimate = result.compensation_estimate;
  const isCleaning = estimate?.category === 'cleaning' || result.cleanliness.level === 'dirty';
  const reviewHref = `/capture/review-request?case_id=${encodeURIComponent(result.case_id)}`;
  const paymentHref = `/capture/payment?case_id=${encodeURIComponent(result.case_id)}`;

  return (
    <ResultShell>
      <section className="px-5 pb-8 pt-5 sm:px-7">
        {appealSubmitted && <output className="mb-4 flex items-start gap-2 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-medium leading-6 text-emerald-800"><Check className="mt-0.5 size-4 shrink-0" />補拍照片已送出，可由人工進一步覆核。</output>}

        <div className="flex items-start gap-4 rounded-[26px] border border-amber-200 bg-amber-50 p-5">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-amber-100 text-amber-700"><AlertTriangle className="size-6" /></span>
          <div><p className="text-sm font-semibold text-amber-800">AI 初步判讀</p><h1 className="mt-1 text-2xl font-semibold leading-tight text-[#31291a]">AI 偵測到 {findings.length} 處疑似問題</h1><p className="mt-2 text-sm leading-6 text-amber-900/70">以下已依問題照片分開列出部位、狀況與預估費用。</p></div>
        </div>

        <div className="mt-6 flex items-end justify-between"><div><p className="text-sm font-semibold text-[#2d6d5d]">問題照片</p><h2 className="mt-1 text-2xl font-semibold">各處問題與估價</h2></div><span className="rounded-full bg-[#e6f0ea] px-3 py-1 text-sm font-semibold text-[#2d6d5d]">共 {findings.length} 處</span></div>

        <div className="mt-4 space-y-4">
          {findings.map((finding, index) => <FindingCard key={finding.id} finding={finding} thumbnail={thumbnails[finding.shot_type]} index={index} overallEstimate={estimate} findingCount={findings.length} />)}
        </div>

        <div className="mt-5 overflow-hidden rounded-[26px] border border-[#cbdad2] bg-white shadow-sm">
          <div className="flex items-center gap-2 bg-[#edf4f0] px-5 py-4 text-[#173e35]"><CircleDollarSign className="size-5" /><h2 className="font-semibold">{isCleaning ? '清潔費用預估總表' : '損壞費用預估總表'}</h2></div>
          <dl className="divide-y divide-[#e1e9e4] px-5">
            {findings.map((finding, index) => {
              const findingEstimate = getFindingEstimate(finding, estimate, index, findings.length);
              return <SummaryRow key={finding.id} label={`${index + 1}. ${finding.summary}`} value={findingEstimate ? formatMoneyRange(findingEstimate.min, findingEstimate.max) : '待估價'} />;
            })}
          </dl>
          <div className="bg-[#173e35] px-5 py-5 text-white">
            <p className="text-sm font-medium text-[#c9ff38]">總共預估費用</p>
            <p className="mt-1 text-[30px] font-semibold tracking-tight">{estimate ? formatMoneyRange(estimate.min, estimate.max) : '待估價'}</p>
            <p className="mt-2 text-sm leading-6 text-white/65">以上為 AI 初步估價範圍，可作為各項問題的費用參考。</p>
          </div>
        </div>

        <div className="mt-4 rounded-[26px] border-2 border-[#9bc52b] bg-[#f5ffe0] p-5 shadow-[0_10px_28px_rgb(105_145_21/12%)]">
          <div className="flex items-center gap-2 text-[#355f54]"><CheckCircle2 className="size-5" /><p className="text-sm font-semibold">進入付款流程的確切金額</p></div>
          <div className="mt-3 flex items-end justify-between gap-4"><h2 className="text-lg font-semibold">最終價格為：</h2><strong className="text-[32px] leading-none tracking-tight text-[#173e35]">{estimate ? formatMoney(resolveFinalAmount(estimate)) : '待確認'}</strong></div>
          <p className="mt-4 border-t border-[#cfe69a] pt-3 text-sm leading-6 text-[#526a61]">若選擇對 AI 判讀結果無異議，付款頁將以此金額收款；如有疑義，可先申請人工覆核。</p>
        </div>

        <div className="mt-7 space-y-3">
          <Link href={reviewHref} className="flex min-h-20 w-full flex-col items-center justify-center rounded-2xl bg-[#c9ff38] px-5 py-3 text-[#10251f] shadow-[0_8px_20px_rgb(113_154_20/18%)] transition hover:bg-[#ddff7d]"><span className="flex items-center gap-2 text-lg font-semibold"><FileSearch className="size-5" />申請人工覆核</span><span className="mt-1 text-sm font-normal text-[#355f54]">若對 AI 判讀結果有疑義，可申請專人重新確認</span></Link>
          <Link href={paymentHref} className="flex min-h-16 w-full items-center justify-center rounded-2xl border border-[#b9cbc2] bg-white px-5 py-3 text-center font-semibold leading-6 text-[#355f54] transition hover:bg-[#f1f6f3]">我對 AI 判讀結果無異議，前往賠款付款</Link>
        </div>
        <p className="mt-4 text-center text-sm text-[#73837c]">案件 {result.case_id} · {formatDate(result.analyzed_at)}</p>
      </section>
    </ResultShell>
  );
}

function FindingCard({ finding, thumbnail, index, overallEstimate, findingCount }: { finding: DamageFinding; thumbnail?: string; index: number; overallEstimate: CompensationEstimate | null; findingCount: number }) {
  const findingEstimate = getFindingEstimate(finding, overallEstimate, index, findingCount);
  return (
    <article className="overflow-hidden rounded-[24px] border border-[#dce6e0] bg-white shadow-sm">
      <div className="relative aspect-[16/9] bg-[#e8efeb]">
        {thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumbnail} alt={`${finding.shot_label}問題照片`} className="size-full object-cover" />
        ) : (
          <div className="grid size-full place-items-center text-center text-[#657970]"><div><ImageIcon className="mx-auto size-8" /><p className="mt-2 text-sm">問題照片縮圖</p></div></div>
        )}
        <span className="absolute left-3 top-3 rounded-full bg-black/65 px-3 py-1.5 text-sm font-medium text-white backdrop-blur">{finding.shot_label}</span>
      </div>
      <div className="p-4">
        <p className="text-sm font-semibold text-amber-700">疑似問題 {index + 1}</p>
        <h3 className="mt-1 text-lg font-semibold leading-6">{finding.summary}</h3>
        <div className="mt-4 flex items-center justify-between rounded-2xl bg-[#f3f7f4] px-4 py-3"><span className="text-sm font-medium text-[#597067]">此處預估費用</span><strong className="text-lg text-[#173e35]">{findingEstimate ? formatMoneyRange(findingEstimate.min, findingEstimate.max) : '待估價'}</strong></div>
        <p className="mt-3 text-sm leading-6 text-[#73837c]">此處為 AI 偵測到的影像差異，費用為初步預估。</p>
      </div>
    </article>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"><dt className="text-sm text-[#62756d]">{label}</dt><dd className="text-right text-sm font-semibold">{value}</dd></div>;
}

function normalizeFindings(result: StoredAnalysisResult): DamageFinding[] {
  if (result.damage_findings?.length) return result.damage_findings;
  const summary = result.vehicle_change.findings[0] ?? result.cleanliness.findings[0] ?? '偵測到需要人工確認的車況';
  return [{ id: `${result.case_id}-fallback`, shot_type: 'rear_right_45', shot_label: '問題照片', summary, confidence: result.confidence, severity: 'medium', photo_id: 'unknown', estimated_cost: result.compensation_estimate ? { currency: 'TWD', min: result.compensation_estimate.min, max: result.compensation_estimate.max } : { currency: 'TWD', min: 0, max: 0 } }];
}

function getFindingEstimate(finding: DamageFinding, overallEstimate: CompensationEstimate | null, index: number, findingCount: number) {
  if (finding.estimated_cost) return finding.estimated_cost;
  if (!overallEstimate) return null;
  const divisor = Math.max(findingCount, 1);
  const isLast = index === findingCount - 1;
  const min = isLast ? overallEstimate.min - Math.floor(overallEstimate.min / divisor) * (divisor - 1) : Math.floor(overallEstimate.min / divisor);
  const max = isLast ? overallEstimate.max - Math.floor(overallEstimate.max / divisor) * (divisor - 1) : Math.floor(overallEstimate.max / divisor);
  return { currency: overallEstimate.currency, min, max };
}

function formatMoneyRange(min: number, max: number) {
  const formatter = new Intl.NumberFormat('zh-TW');
  return `NT$${formatter.format(min)}–${formatter.format(max)}`;
}

function formatMoney(amount: number) {
  return `NT$${new Intl.NumberFormat('zh-TW').format(amount)}`;
}

function resolveFinalAmount(estimate: CompensationEstimate) {
  return estimate.final_amount ?? Math.round((estimate.min + estimate.max) / 200) * 100;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date);
}
