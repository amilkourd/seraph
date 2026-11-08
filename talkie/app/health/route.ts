// contracts/api.md: every service exposes GET /health → {ok:true, mock:bool}.
export function GET() {
  const transport = process.env.NEXT_PUBLIC_TALKIE_TRANSPORT ?? "mock";
  return Response.json(
    { ok: true, mock: transport !== "livekit", service: "talkie", transport },
    { headers: { "cache-control": "no-store" } },
  );
}
