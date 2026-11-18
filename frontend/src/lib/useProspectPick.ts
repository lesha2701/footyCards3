import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";

import { fetchProspect, type Prospect } from "@/api/prospect";

/** The «Воспитанник Академии» as an option of a mini-game's card picker
 * (Пенальти, Штрафной, «Атака 1 на 1» — like «Ответка»): `prospect` is
 * null while the user has none. `?prospect=1` (from his page) starts with
 * him straight away — `startProspect` runs once; `holdPicker` keeps the
 * picker closed meanwhile. `active`: the picker is up (no series yet). */
export function useProspectPick(active: boolean, startProspect: () => void) {
  const [params] = useSearchParams();
  const wantsProspect = params.get("prospect") === "1";
  const { data: view, isLoading } = useQuery({ queryKey: ["prospect"], queryFn: fetchProspect, enabled: active });
  const prospect: Prospect | null = view?.enabled ? view.prospect : null;

  const autoStarted = useRef(false);
  useEffect(() => {
    if (active && wantsProspect && prospect && !autoStarted.current) {
      autoStarted.current = true;
      startProspect();
    }
  }, [active, wantsProspect, prospect, startProspect]);

  return { prospect, holdPicker: wantsProspect && (prospect !== null || isLoading) };
}

/** His name and number on the kicker's back (as shirtPrint does for a card). */
export function prospectPrint(name: string | null | undefined, prospect: Prospect | null): { name: string; number: number } {
  return { name: name ?? prospect?.name ?? "", number: prospect?.number ?? 10 };
}
