'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  LoaderCircle,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  clearCaptureDraft,
  readCaptureDraft,
  saveCaptureResult,
  saveCaptureThumbnails,
  type CaptureDraft,
  type StoredAnalysisResult,
} from '@/lib/capture-flow';
import { analyses, nextStatus } from '@/lib/prototype';

export default function AnalysisDemoPage() {
  const [draft, setDraft] = useState<CaptureDraft | null>(null);
  const [selected, setSelected] = useState<'success' | 'failure' | null>(null);

  useEffect(() => {
    setDraft(readCaptureDraft());
  }, []);

  function chooseResult(outcome: 'success' | 'failure') {
    setSelected(outcome);
    const analysis = outcome === 'success' ? analyses.normal : analyses.damage;
    const result: StoredAnalysisResult = {
      ...analysis,
      status: nextStatus(analysis.recommended_action),
      analyzed_at: new Date().toISOString(),
      source: 'mock-ui',
    };
    saveCaptureResult(result);
    saveCaptureThumbnails(result.case_id, draft?.thumbnails ?? {});
    clearCaptureDraft();
    window.location.assign(`/capture/result?case_id=${encodeURIComponent(result.case_id)}`);
  }

  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white">
          <div className="grid grid-cols-[44px_1fr_44px] items-center">
            <Link href="/capture/camera" aria-label="返回拍攝頁" className="grid size-11 place-items-center rounded-2xl border border-white/15 bg-white/10 transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[#c9ff38]/60">
              <ArrowLeft className="size-5" aria-hidden="true" />
            </Link>
            <div className="text-center"><p className="font-semibold">分析結果</p><p className="mt-0.5 text-sm text-white/55">暫時示範介面</p></div>
            <span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><ShieldCheck className="size-5" aria-hidden="true" /></span>
          </div>
        </header>

        <section className="flex min-h-[calc(100dvh-76px)] flex-col justify-center px-5 py-10 sm:min-h-[650px] sm:px-7">
          <div className="text-center">
            <p className="text-sm font-semibold tracking-wide text-[#2d6d5d]">照片已送出</p>
            <h1 className="mt-2 text-[30px] font-semibold leading-tight tracking-tight">請選擇本次分析結果</h1>
            <p className="mx-auto mt-3 max-w-sm text-base leading-7 text-[#62756d]">目前尚未串接後端判斷資料，先使用下方兩個選項測試後續畫面。</p>
            <p className="mt-3 text-sm font-medium text-[#2d6d5d]">本次已拍攝 {draft?.photoCount ?? 2} 張照片</p>
          </div>

          <div className="mt-8 grid gap-4">
            <Button
              className="h-24 w-full justify-start rounded-[24px] bg-[#dfff8b] px-6 text-left text-[#10251f] shadow-[0_10px_24px_rgb(105_145_21/15%)] hover:bg-[#cfff55]"
              onClick={() => chooseResult('success')}
              disabled={selected !== null}
            >
              {selected === 'success' ? <LoaderCircle className="size-8 animate-spin" /> : <CheckCircle2 className="size-8" />}
              <span><strong className="block text-xl">成功</strong><span className="mt-1 block text-sm font-normal text-[#355f54]">進入完成還車檢查</span></span>
            </Button>

            <Button
              className="h-24 w-full justify-start rounded-[24px] bg-[#173e35] px-6 text-left text-white shadow-[0_10px_24px_rgb(23_62_53/18%)] hover:bg-[#22594b]"
              onClick={() => chooseResult('failure')}
              disabled={selected !== null}
            >
              {selected === 'failure' ? <LoaderCircle className="size-8 animate-spin" /> : <XCircle className="size-8 text-[#c9ff38]" />}
              <span><strong className="block text-xl">失敗</strong><span className="mt-1 block text-sm font-normal text-white/65">進入分析結果介面</span></span>
            </Button>
          </div>
        </section>
      </div>
    </main>
  );
}
