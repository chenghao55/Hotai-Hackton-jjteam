'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Landmark,
  MessageCircle,
  ShieldCheck,
  Smartphone,
  WalletCards,
} from 'lucide-react';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { readCaptureResult, type StoredAnalysisResult } from '@/lib/capture-flow';
import { analyses } from '@/lib/prototype';

type PaymentMethod = 'bank' | 'line-pay' | 'apple-pay';

const paymentMethods = [
  { id: 'bank' as const, title: '銀行轉帳', description: '取得本案件專屬轉帳帳號', icon: Landmark, tag: '所有銀行' },
  { id: 'line-pay' as const, title: 'LINE Pay', description: '使用 LINE Pay 應用程式完成付款', icon: MessageCircle, tag: '快速付款' },
  { id: 'apple-pay' as const, title: 'Apple Pay', description: '使用裝置錢包安全完成付款', icon: Smartphone, tag: 'Apple 裝置' },
];

export default function CapturePaymentPage() {
  const [result, setResult] = useState<StoredAnalysisResult | null>(null);
  const [caseId, setCaseId] = useState(analyses.damage.case_id);
  const [method, setMethod] = useState<PaymentMethod>('bank');
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    const requestedCaseId = new URLSearchParams(window.location.search).get('case_id') || analyses.damage.case_id;
    setCaseId(requestedCaseId);
    setResult(readCaptureResult(requestedCaseId));
  }, []);

  const estimate = result?.compensation_estimate ?? analyses.damage.compensation_estimate;
  const backHref = `/capture/result?case_id=${encodeURIComponent(caseId)}`;
  const selectedMethod = paymentMethods.find((item) => item.id === method)!;

  return (
    <main className="min-h-screen bg-[#edf3ef] text-[#10251f] sm:px-5 sm:py-8">
      <div className="mx-auto min-h-dvh w-full max-w-md overflow-hidden bg-white shadow-[0_0_50px_rgb(16_37_31/10%)] sm:min-h-[calc(100dvh-4rem)] sm:rounded-[32px]">
        <header className="bg-[#101d1a] px-5 py-4 text-white">
          <div className="grid grid-cols-[44px_1fr_44px] items-center">
            <Link href={backHref} aria-label="返回 AI 判讀結果" className="grid size-11 place-items-center rounded-2xl border border-white/15 bg-white/10 transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[#c9ff38]/60"><ArrowLeft className="size-5" /></Link>
            <div className="text-center"><p className="font-semibold">賠款付款</p><p className="mt-0.5 text-sm text-white/55">案件 {caseId}</p></div>
            <span className="grid size-11 place-items-center rounded-2xl bg-[#c9ff38] text-[#10251f]"><WalletCards className="size-5" /></span>
          </div>
        </header>

        <section className="px-5 pb-9 pt-6 sm:px-7">
          <div className="rounded-[28px] bg-[#173e35] p-5 text-white shadow-[0_14px_34px_rgb(23_62_53/20%)]">
            <p className="text-sm font-medium text-[#c9ff38]">本次最終應付金額</p>
            <p className="mt-2 text-[38px] font-semibold tracking-tight">{estimate ? formatMoney(estimate.final_amount ?? Math.round((estimate.min + estimate.max) / 200) * 100) : '待確認'}</p>
            <p className="mt-3 text-sm leading-6 text-white/65">此為本次付款使用的確切金額，選擇付款方式後將以此金額繼續。</p>
          </div>

          <div className="mt-7">
            <p className="text-sm font-semibold text-[#2d6d5d]">付款設定</p>
            <h1 className="mt-1 text-[28px] font-semibold leading-tight tracking-tight">選擇付款方式</h1>
            <p className="mt-2 text-base leading-7 text-[#62756d]">請選擇一種方式，確認後再進入對應的安全付款流程。</p>
          </div>

          <RadioGroup value={method} onValueChange={(value) => { setMethod(value as PaymentMethod); setConfirmed(false); }} className="mt-5 gap-3" aria-label="付款方式">
            {paymentMethods.map((item) => {
              const Icon = item.icon;
              const selected = method === item.id;
              return (
                <label key={item.id} className={`flex cursor-pointer items-center gap-4 rounded-[22px] border p-4 transition ${selected ? 'border-[#8fb624] bg-[#f5ffe0] shadow-[0_6px_18px_rgb(95_130_18/10%)]' : 'border-[#d8e4dd] bg-white hover:bg-[#f7faf8]'}`}>
                  <span className={`grid size-12 shrink-0 place-items-center rounded-2xl ${selected ? 'bg-[#c9ff38] text-[#173e35]' : 'bg-[#edf4f0] text-[#45645b]'}`}><Icon className="size-6" /></span>
                  <span className="min-w-0 flex-1"><span className="flex items-center gap-2"><strong className="text-base">{item.title}</strong><span className="rounded-full bg-white/80 px-2 py-0.5 text-xs font-medium text-[#60736b]">{item.tag}</span></span><span className="mt-1 block text-sm leading-5 text-[#62756d]">{item.description}</span></span>
                  <RadioGroupItem value={item.id} aria-label={item.title} className="size-5 border-[#8ba095] data-checked:border-[#173e35] data-checked:bg-[#173e35]" />
                </label>
              );
            })}
          </RadioGroup>

          {confirmed && <output className="mt-5 flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-medium leading-6 text-emerald-800"><Check className="mt-0.5 size-5 shrink-0" />已選擇 {selectedMethod.title}。正式串接金流後，將從這裡安全前往付款。</output>}

          <button type="button" onClick={() => setConfirmed(true)} className="mt-7 inline-flex min-h-16 w-full items-center justify-center gap-2 rounded-2xl bg-[#173e35] px-5 py-3 text-lg font-semibold text-white shadow-[0_10px_24px_rgb(23_62_53/18%)] transition hover:bg-[#22594b]">確認付款方式並繼續<ChevronRight className="size-5" /></button>
          <div className="mt-4 flex items-start gap-3 rounded-2xl bg-[#f1f6f3] p-4 text-sm leading-6 text-[#526a61]"><ShieldCheck className="mt-0.5 size-5 shrink-0 text-[#2d6d5d]" /><p>目前為付款介面展示，不會產生實際扣款，也不會要求輸入銀行密碼。</p></div>
        </section>
      </div>
    </main>
  );
}

function formatMoney(amount: number) {
  return `NT$${new Intl.NumberFormat('zh-TW').format(amount)}`;
}
