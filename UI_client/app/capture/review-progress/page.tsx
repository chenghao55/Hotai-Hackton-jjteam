'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  Bell,
  Check,
  CircleDollarSign,
  ClipboardCheck,
  FileCheck2,
  ShieldCheck,
  UserRoundCheck,
} from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { analyses } from '@/lib/prototype';

const stages = [
  { key: 'UNASSIGNED', title: '覆核申請已送出', description: '系統已完整收到案件與問題照片。', icon: FileCheck2 },
  { key: 'DISPATCHED', title: '已指派審核人員', description: '案件已送交營運專員處理。', icon: UserRoundCheck },
  { key: 'PROCESSING', title: '人工審核中', description: '正在比對問題照片、車況與費用。', icon: ClipboardCheck },
  { key: 'PENDING_PAYMENT', title: '等待付款確認', description: '覆核完成後，將顯示最終金額與付款方式。', icon: CircleDollarSign },
  { key: 'COMPLETED', title: '案件完成', description: '費用與車況處理記錄已完成建立。', icon: ShieldCheck },
] as const;

const currentStageIndex = 2;

export default function ReviewProgressPage() {
  const [caseId, setCaseId] = useState(analyses.damage.case_id);

  useEffect(() => {
    setCaseId(new URLSearchParams(window.location.search).get('case_id') || analyses.damage.case_id);
  }, []);

  const backHref = `/capture/result?case_id=${encodeURIComponent(caseId)}`;
  const progress = ((currentStageIndex + 1) / stages.length) * 100;

  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white">
          <div className="grid grid-cols-[44px_1fr_44px] items-center">
            <Link href={backHref} aria-label="返回 AI 判讀結果" className="grid size-11 place-items-center rounded-2xl border border-white/15 bg-white/10 transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[#c9ff38]/60"><ArrowLeft className="size-5" /></Link>
            <div className="text-center"><p className="font-semibold">案件追蹤進度</p><p className="mt-0.5 text-sm text-white/55">案件 {caseId}</p></div>
            <span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><ClipboardCheck className="size-5" /></span>
          </div>
        </header>

        <section className="px-5 pb-9 pt-6 sm:px-7">
          <div className="rounded-[28px] bg-[#173e35] p-5 text-white shadow-[0_14px_34px_rgb(23_62_53/20%)]">
            <div className="flex items-center justify-between gap-4"><div><p className="text-sm font-medium text-[#c9ff38]">目前進度</p><h1 className="mt-1 text-[28px] font-semibold leading-tight">人工審核中</h1></div><span className="grid size-12 place-items-center rounded-2xl bg-white/10"><ClipboardCheck className="size-6 text-[#c9ff38]" /></span></div>
            <Progress value={progress} className="mt-5 h-2.5 bg-white/15 [&>div]:bg-[#c9ff38]" />
            <div className="mt-2 flex justify-between text-sm text-white/60"><span>已完成 3 / 5 階段</span><span>{Math.round(progress)}%</span></div>
          </div>

          <div className="mt-7">
            <p className="text-sm font-semibold text-[#2d6d5d]">覆核流程</p>
            <h2 className="mt-1 text-2xl font-semibold">案件處理時間軸</h2>
          </div>

          <ol className="mt-5">
            {stages.map((stage, index) => {
              const Icon = stage.icon;
              const completed = index < currentStageIndex;
              const current = index === currentStageIndex;
              return (
                <li key={stage.key} className="relative grid grid-cols-[44px_1fr] gap-3 pb-5 last:pb-0">
                  {index < stages.length - 1 && <span className={`absolute left-[21px] top-10 h-[calc(100%-24px)] w-0.5 ${index < currentStageIndex ? 'bg-[#8bb51c]' : 'bg-[#dce7e1]'}`} aria-hidden="true" />}
                  <span className={`relative z-10 grid size-11 place-items-center rounded-full border-2 ${completed ? 'border-[#8bb51c] bg-[#dfff8b] text-[#173e35]' : current ? 'border-[#173e35] bg-[#173e35] text-[#c9ff38] shadow-[0_0_0_5px_rgb(201_255_56/25%)]' : 'border-[#d4e1da] bg-white text-[#9aaba3]'}`}>{completed ? <Check className="size-5" /> : <Icon className="size-5" />}</span>
                  <div className={`rounded-2xl border p-4 ${current ? 'border-[#b8cf5f] bg-[#f7ffe8]' : 'border-[#e0e9e4] bg-[#f9fbfa]'}`}>
                    <div className="flex items-center justify-between gap-3"><h3 className={`font-semibold ${index > currentStageIndex ? 'text-[#819087]' : 'text-[#173e35]'}`}>{stage.title}</h3>{current && <span className="shrink-0 rounded-full bg-[#c9ff38] px-2.5 py-1 text-xs font-semibold text-[#173e35]">進行中</span>}</div>
                    <p className={`mt-1 text-sm leading-6 ${index > currentStageIndex ? 'text-[#9aa8a1]' : 'text-[#62756d]'}`}>{stage.description}</p>
                  </div>
                </li>
              );
            })}
          </ol>

          <div className="mt-7 flex items-start gap-3 rounded-2xl border border-[#d8e5de] bg-[#f1f6f3] p-4 text-sm leading-6 text-[#526a61]"><Bell className="mt-0.5 size-5 shrink-0 text-[#2d6d5d]" /><p>覆核進度更新或結果確認後，系統會透過已設定的通知方式告知你。</p></div>
          <Link href="/" className="mt-5 inline-flex min-h-16 w-full items-center justify-center rounded-2xl border border-[#b9cbc2] bg-white px-5 py-3 text-center text-lg font-semibold text-[#355f54] transition hover:bg-[#f1f6f3]">先返回首頁，等待覆核結果通知</Link>
        </section>
      </div>
    </main>
  );
}
