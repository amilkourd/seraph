import { Suspense } from "react";
import type { Metadata } from "next";
import { WebCall } from "./web-call";

export const metadata: Metadata = { title: "Appel pompiers · exercice" };

export default function CallPage() {
  return (
    <Suspense fallback={<main className="h-dvh bg-black" />}>
      <WebCall />
    </Suspense>
  );
}
