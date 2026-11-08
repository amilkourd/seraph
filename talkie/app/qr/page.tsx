// `/qr` — a big QR to the occupants replica's public opt-in page (`OCCUPANTS_PUBLIC_URL` + `/inscription`).
// Visitors scan it, sign up, and Rosetta reads them back through the screen (`occupants.list`).
// `?url=https://…` overrides the env for a quick fix on stage.
import { Suspense } from "react";
import type { Metadata } from "next";
import { connection } from "next/server";
import QRCode from "qrcode";

export const metadata: Metadata = { title: "Inscription occupants · exercice" };

const PLACEHOLDER = "https://occupants.exemple.invalid";

function inscriptionUrl(base: string): string {
  const b = base.trim().replace(/\/+$/, "");
  return b.endsWith("/inscription") ? b : `${b}/inscription`;
}

function safeHttpUrl(v: unknown): string | null {
  if (typeof v !== "string" || !v) return null;
  try {
    const u = new URL(v);
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : null;
  } catch {
    return null;
  }
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default function QrPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <Suspense fallback={<main className="h-dvh bg-black" />}>
      <Qr searchParams={searchParams} />
    </Suspense>
  );
}

async function Qr({ searchParams }: { searchParams: SearchParams }) {
  await connection(); // read the env at request time, not at build time
  const sp = await searchParams;
  const override = safeHttpUrl(sp.url);
  const envBase = process.env.OCCUPANTS_PUBLIC_URL?.trim() || "";
  const placeholder = !override && !envBase;
  const url = inscriptionUrl(override ?? (envBase || PLACEHOLDER));
  const svg = await QRCode.toString(url, {
    type: "svg",
    errorCorrectionLevel: "M",
    margin: 0,
    color: { dark: "#0b0a0a", light: "#ffffff" },
  });

  return (
    <main className="safe-x safe-top safe-bottom flex min-h-dvh flex-col items-center justify-center gap-[3vh] bg-black text-center">
      <span className="radio-label rounded-[5px] border border-white px-2.5 py-1 text-[clamp(14px,1.6vw,20px)] text-white">
        Exercice
      </span>
      <h1
        className="max-w-[18ch] text-[clamp(26px,4.4vw,56px)] leading-[1.02] font-[520] text-white"
        style={{ fontFamily: "var(--font-archivo)", fontStretch: "108%", letterSpacing: "-0.03em" }}
      >
        Scannez. Inscrivez-vous. Gabriel vous appelle.
      </h1>

      <div
        className="rounded-[18px] bg-white p-[clamp(14px,2.4vmin,28px)]"
        style={{ width: "min(80vw, 58vh, 640px)" }}
      >
        <div className="aspect-square w-full [&>svg]:h-full [&>svg]:w-full" dangerouslySetInnerHTML={{ __html: svg }} />
      </div>

      {placeholder && (
        <p className="radio-label rounded-[6px] border border-white px-3 py-2 text-[15px] text-white">
          QR factice · OCCUPANTS_PUBLIC_URL vide
        </p>
      )}
    </main>
  );
}
