import { Suspense } from "react";
import { CrewRadio } from "./crew-radio";

export default function Page() {
  return (
    <Suspense fallback={<main className="h-dvh bg-black" />}>
      <CrewRadio />
    </Suspense>
  );
}
