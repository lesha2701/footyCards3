import { describe } from "@/lib/freeKick3d/crashLog";

/** The scene failed: what threw (all logged errors, first first) and a restart. */
export default function SceneCrash({ error, retry, log }: { error: Error; retry: () => void; log: string[] }) {
  const entries = log.length ? log : [describe(error)];
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-bg-base p-6 text-center">
      <div className="font-display text-lg">Сцена упала</div>
      <pre className="max-h-[55vh] w-full overflow-auto whitespace-pre-wrap break-all rounded-lg bg-bg-surface p-3 text-left text-micro text-ink-mist">
        {entries.map((e, i) => `${i + 1}. ${e}`).join("\n\n")}
      </pre>
      <button type="button" onClick={retry} className="rounded-xl bg-accent px-5 py-3 font-semibold text-black">
        Перезапустить сцену
      </button>
    </div>
  );
}
