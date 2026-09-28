'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Camera, ShieldCheck } from 'lucide-react';
import { buttonVariants } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';

const captureRules = [
  { title: '依照畫面順序拍攝', description: '請依系統指示完成卡片、車內與車身指定角度，請勿跳過必要照片。' },
  { title: '保持正確角度與距離', description: '拍攝車外時，建議與車身保持約 2 至 3 公尺距離，並依提示以 45 度角拍攝，確保完整車身都在畫面內。' },
  { title: '確認光線充足', description: '避免逆光、過暗或強烈反光。夜間請移至有照明的位置，必要時開啟手機閃光燈。' },
  { title: '照片必須清楚', description: '拍攝時請拿穩手機並等待對焦完成。若照片模糊、晃動或遭手指遮擋，系統會請你重新拍攝。' },
  { title: '保留車牌與車況細節', description: '車牌、保險桿、輪圈及車身表面應清楚可見；若發現刮痕、凹陷或污損，請另外近距離補拍。' },
  { title: '整理並拍攝車內', description: '請先帶走個人物品，再完整拍攝前座、後座與腳踏區，避免物品遮住需要檢查的位置。' },
  { title: '使用原始照片', description: '請直接使用手機相機拍攝，不要套用濾鏡、裁切、塗改或使用通訊軟體壓縮後的圖片。' },
  { title: '注意拍攝安全', description: '請先將車輛停妥並確認周遭安全，不要站在車道中央或一邊駕駛一邊操作手機。' },
];

export default function CapturePage() {
  const [hasReadRules, setHasReadRules] = useState(false);
  const [hasReachedRulesEnd, setHasReachedRulesEnd] = useState(false);
  const [rulesError, setRulesError] = useState('');
  const rulesScrollRef = useRef<HTMLDivElement>(null);

  function updateRulesEndState() {
    const element = rulesScrollRef.current;
    if (!element || element.scrollHeight === 0 || element.clientHeight === 0) return;
    if (element.scrollTop + element.clientHeight >= element.scrollHeight - 4) {
      setHasReachedRulesEnd(true);
      setRulesError('');
    }
  }

  useEffect(() => {
    updateRulesEndState();
    window.addEventListener('resize', updateRulesEndState);
    return () => window.removeEventListener('resize', updateRulesEndState);
  }, []);

  function changeRulesConfirmation(checked: boolean) {
    if (checked && !hasReachedRulesEnd) {
      setRulesError('請先詳細閱讀所有條款');
      return;
    }
    setHasReadRules(checked);
    setRulesError('');
  }

  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col overflow-x-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white">
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#c9ff38] text-[#10251f]"><ShieldCheck className="size-6" aria-hidden="true" /></span>
              <div className="min-w-0"><p className="text-lg font-semibold tracking-tight">車況管家</p><p className="text-sm text-white/55">iRent AI Prototype</p></div>
            </div>
            <span className="shrink-0 rounded-full border border-white/15 px-3 py-1.5 text-sm text-white/70">拍攝者介面</span>
          </div>
        </header>

        <section className="flex flex-1 flex-col px-5 pb-6 pt-5 sm:px-7">
          <div><p className="text-sm font-semibold text-[#2d6d5d]">拍攝前確認</p><h1 className="mt-1.5 text-[28px] font-semibold leading-tight tracking-tight">開始拍照前，<br />請先閱讀拍攝規則</h1><p className="mt-2 text-base leading-6 text-[#62756d]">依照規則拍攝，可減少照片模糊、角度不完整及重拍的情況。</p></div>
          <div className="relative mt-4 flex h-[50dvh] min-h-[340px] max-h-[520px] shrink-0 flex-col overflow-hidden rounded-[26px] border border-[#cbe5d7] bg-[#effaf3] shadow-[inset_0_1px_0_rgb(255_255_255/80%)]">
            <div className="flex items-center gap-3 border-b border-[#cbe5d7] bg-[#ddf5e6] px-5 py-3">
              <span className="grid size-9 place-items-center rounded-xl bg-[#173e35] text-[#c9ff38]"><Camera className="size-5" aria-hidden="true" /></span>
              <div><h2 className="font-semibold">拍照規則及流程</h2><p className="text-sm text-[#587066]">共 8 項，請向下閱讀完整內容</p></div>
            </div>
            <div ref={rulesScrollRef} data-testid="rules-scroll-area" onScroll={updateRulesEndState} className="min-h-0 flex-1 touch-pan-y overflow-y-scroll overscroll-contain px-5 py-1 [scrollbar-color:#7aa291_#dcefe4] [scrollbar-width:auto] [-webkit-overflow-scrolling:touch]">
              <ol className="divide-y divide-[#cbe5d7]">
                {captureRules.map((rule, index) => <li key={rule.title} className="flex gap-3 py-4"><span className="grid size-7 shrink-0 place-items-center rounded-full bg-[#c9ff38] text-sm font-bold text-[#173e35]" aria-hidden="true">{index + 1}</span><div><h3 className="text-base font-semibold">{rule.title}</h3><p className="mt-1 text-[15px] leading-6 text-[#50675e]">{rule.description}</p></div></li>)}
              </ol>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3 rounded-2xl px-1 py-2 text-base font-medium leading-6">
            <Checkbox aria-labelledby="rules-confirmation-label" aria-describedby={rulesError ? 'rules-confirmation-error' : undefined} aria-invalid={Boolean(rulesError)} checked={hasReadRules} onCheckedChange={(checked) => changeRulesConfirmation(checked === true)} className="size-7 rounded-full border-2 border-[#49675e] bg-white text-[#10251f] data-checked:border-[#c9ff38] data-checked:bg-[#c9ff38] [&_svg]:size-4" />
            <span id="rules-confirmation-label">我已經詳細閱讀拍照規則及流程</span>
          </div>
          {rulesError && <p id="rules-confirmation-error" role="alert" className="mt-1 px-1 text-sm font-medium text-red-600">{rulesError}</p>}
          {hasReadRules ? (
            <Link href="/capture/camera" className={cn(buttonVariants(), 'mt-3 h-14 w-full rounded-2xl bg-[#173e35] text-base font-semibold text-white shadow-[0_8px_20px_rgb(23_62_53/18%)] hover:bg-[#22594b] focus-visible:ring-[#8db6aa]')}>開始拍照 <ArrowRight className="size-5" aria-hidden="true" /></Link>
          ) : (
            <button type="button" disabled className={cn(buttonVariants(), 'mt-3 h-14 w-full cursor-not-allowed rounded-2xl bg-[#d7ddd9] text-base font-semibold text-[#87928d] shadow-none disabled:opacity-100')}>開始拍照 <ArrowRight className="size-5" aria-hidden="true" /></button>
          )}
        </section>
      </div>
    </main>
  );
}
