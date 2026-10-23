import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAdminCoaches, fetchAdminPlayers, fetchAdminStadiums } from "@/admin/api";

export type LinkKind = "stadium" | "coach" | "player";

const input = "w-full rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none";

/** Picks a stadium / coach / player by name search (admin). */
export default function LinkPicker({
  kind, value, onChange,
}: {
  kind: LinkKind;
  value: number | null;
  onChange: (id: number | null) => void;
}) {
  const [search, setSearch] = useState("");
  const { data } = useQuery({
    queryKey: ["admin-link-picker", kind, search],
    queryFn: async () => {
      const page = kind === "stadium" ? await fetchAdminStadiums(search, 1)
        : kind === "coach" ? await fetchAdminCoaches(search, 1) : await fetchAdminPlayers(search, 1);
      return page.items.map((i) => ({ id: i.id, name: i.display_name }));
    },
  });
  return (
    <div className="flex flex-col gap-1">
      <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск по имени" className={input} />
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)} className={input}>
        <option value="">—</option>
        {value && !data?.some((i) => i.id === value) && <option value={value}>#{value}</option>}
        {data?.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
      </select>
    </div>
  );
}
