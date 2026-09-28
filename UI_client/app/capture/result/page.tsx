'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AlertTriangle, ArrowRight, CheckCircle2, Image as ImageIcon, LoaderCircle, ShieldCheck } from 'lucide-react';
import { readCaptureResult, readCaptureThumbnails } from '@/lib/capture-flow';
import type { CaseResponse, DetectionResponse } from '@/lib/module-e-api';

const statusLabels: Record<CaseResponse['status'], string> = {
  unassigned: '未指派',
  dispatched: '已派工',
  processing: '處理中',
  pending_payment: '待付款',
  completed: '已完成',
};

const categoryLabels: Record<DetectionResponse['category'], string> = {
  scratch: '刮痕',
  collision_damage: '碰撞損傷',
  cleanliness: '清潔問題',
};

const severityLabels: Record<DetectionResponse['severity'], string> = {
  minor: '輕微',
  moderate: '中度',
  severe: '嚴重',
};

const reviewLabels: Record<DetectionResponse['review_state'], string> = {
  needs_review: '待人工覆核',
  auto_accepted: 'AI 自動接受',
  confirmed: '人工確認',
  rejected: '人工駁回',
  corrected: '人工修正',
};

export default function CaptureResultPage() {
  const [result, setResult] = useState<CaseResponse | null>(null);
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const caseId = new URLSearchParams(window.location.search).get('case_id');
    const stored = readCaptureResult(caseId);
    setResult(stored);
    if (stored) setThumbnails(readCaptureThumbnails(stored.case_id));
    setLoading(false);
  }, []);

  if (loading) return <ResultState icon={<LoaderCircle className="size-9 animate-spin" />} title="正在整理檢查結果…" />;
  if (!result) return <MissingResult />;

  return (
    <ResultShell>
      <section className="px-5 pb-8 pt-7 sm:px-7">
        <div className="text-center">
          <span className="mx-auto grid size-20 place-items-center rounded-full bg-[#dfff8b] text-[#173e35]"><CheckCircle2 className="size-10" /></span>
          <p className="mt-5 text-sm font-semibold text-[#2d6d5d]">案件已建立</p>
          <h1 className="mt-2 text-[30px] font-semibold">車況分析結果</h1>
          <p className="mt-2 text-[#62756d]">以下內容直接來自後端 Case，不包含前端推估。</p>
        </div>

        <div className="mt-7 rounded-[26px] border border-[#dce9e1] bg-[#f7faf8] p-5">
          <div className="flex items-center justify-between gap-3"><h2 className="font-semibold">案件摘要</h2><span className="rounded-full bg-[#e2f5e8] px-3 py-1 text-sm font-semibold text-[#276a5a]">{statusLabels[result.status]}</span></div>
          <dl className="mt-5 divide-y divide-[#dfe9e3]">
            <SummaryRow label="案件編號" value={result.case_id} />
            <SummaryRow label="優先分數" value={result.priority_score === null ? '尚未計算' : String(result.priority_score)} />
            <SummaryRow label="付款金額" value={`NT$${new Intl.NumberFormat('zh-TW').format(result.payment_amount)}`} />
            <SummaryRow label="偵測數量" value={`${result.detections.length} 筆`} />
          </dl>
        </div>

        <div className="mt-7"><p className="text-sm font-semibold text-[#2d6d5d]">AI 偵測</p><h2 className="mt-1 text-2xl font-semibold">車況項目</h2></div>
        {result.detections.length === 0 ? (
          <div className="mt-4 rounded-[24px] border border-[#dce9e1] bg-white p-6 text-center text-[#62756d]">目前 Case 沒有偵測到車況項目。</div>
        ) : (
          <div className="mt-4 space-y-4">
            {result.detections.map((detection) => <DetectionCard key={detection.detection_id} detection={detection} thumbnail={thumbnails[detection.source_photo_id ?? detection.return_photo_id]} />)}
          </div>
        )}

        <Link href="/" className="mt-7 inline-flex h-16 w-full items-center justify-center gap-2 rounded-2xl bg-[#173e35] px-5 text-lg font-semibold text-white">返回首頁 <ArrowRight className="size-5" /></Link>
      </section>
    </ResultShell>
  );
}

function DetectionCard({ detection, thumbnail }: { detection: DetectionResponse; thumbnail?: string }) {
  return (
    <article className="overflow-hidden rounded-[24px] border border-[#dce6e0] bg-white shadow-sm">
      <div className="relative aspect-[16/9] bg-[#e8efeb]">
        {thumbnail ? <img src={thumbnail} alt="偵測來源照片" className="size-full object-cover" /> : <div className="grid size-full place-items-center text-[#657970]"><div className="text-center"><ImageIcon className="mx-auto size-8" /><p className="mt-2 text-sm">沒有本機縮圖</p></div></div>}
        <span className="absolute left-3 top-3 rounded-full bg-black/65 px-3 py-1.5 text-sm font-medium text-white">{reviewLabels[detection.review_state]}</span>
      </div>
      <div className="p-5">
        <h3 className="text-xl font-semibold">{categoryLabels[detection.category]}</h3>
        <dl className="mt-4 divide-y divide-[#e1e9e4]">
          <SummaryRow label="嚴重程度" value={severityLabels[detection.severity]} />
          <SummaryRow label="AI 信心" value={`${Math.round(detection.confidence * 100)}%`} />
          <SummaryRow label="偵測編號" value={detection.detection_id} />
          <SummaryRow label="來源照片" value={detection.source_photo_id ?? detection.return_photo_id} />
          {detection.reviewed_category && <SummaryRow label="覆核類別" value={categoryLabels[detection.reviewed_category]} />}
          {detection.reviewed_severity && <SummaryRow label="覆核嚴重度" value={severityLabels[detection.reviewed_severity]} />}
          {detection.review_note && <SummaryRow label="覆核備註" value={detection.review_note} />}
        </dl>
      </div>
    </article>
  );
}

function ResultShell({ children }: { children: React.ReactNode }) {
  return <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8"><div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:rounded-[32px]"><header className="bg-[#101d1a] px-5 py-4 text-white"><div className="flex items-center gap-3"><span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><ShieldCheck className="size-5" /></span><div><p className="font-semibold">車況管家</p><p className="text-sm text-white/55">還車檢查結果</p></div></div></header>{children}</div></main>;
}

function ResultState({ icon, title }: { icon: React.ReactNode; title: string }) {
  return <ResultShell><div className="grid min-h-[70dvh] place-items-center px-8 text-center" role="status"><div className="text-[#2d6d5d]">{icon}<p className="mt-4 font-semibold">{title}</p></div></div></ResultShell>;
}

function MissingResult() {
  return <ResultShell><section className="grid min-h-[70dvh] place-items-center px-6 py-10 text-center"><div><AlertTriangle className="mx-auto size-12 text-amber-700" /><h1 className="mt-5 text-2xl font-semibold">找不到本次案件結果</h1><p className="mt-2 text-[#62756d]">請返回拍攝流程重新建立案件。</p><Link href="/capture/camera" className="mt-7 inline-flex h-14 items-center justify-center rounded-2xl bg-[#173e35] px-5 font-semibold text-white">返回拍攝流程</Link></div></section></ResultShell>;
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"><dt className="text-sm text-[#62756d]">{label}</dt><dd className="break-all text-right text-sm font-semibold">{value}</dd></div>;
}
