import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchFriendRelation, removeFriend, sendFriendRequest } from "@/api/friends";
import { IconUsers } from "@/components/icons";
import { haptic } from "@/lib/telegram";

/** Friend action on a public profile: add / requested / accept / friends. */
export default function FriendButton({ userId }: { userId: number }) {
  const queryClient = useQueryClient();
  const { data: relation } = useQuery({ queryKey: ["friends", "relation", userId], queryFn: () => fetchFriendRelation(userId) });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["friends"] });
    queryClient.invalidateQueries({ queryKey: ["attention"] });
  };
  const add = useMutation({ mutationFn: () => sendFriendRequest(userId), onSuccess: () => { haptic("light"); refresh(); } });
  const remove = useMutation({ mutationFn: () => removeFriend(userId), onSuccess: refresh });
  if (!relation) return null;

  const base = "mt-2 flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-bold active:scale-95 disabled:opacity-50";
  if (relation === "friends") {
    return (
      <button onClick={() => remove.mutate()} disabled={remove.isPending} className={`${base} bg-white/5 text-ink-mist`}>
        <IconUsers size={14} /> В друзьях · убрать
      </button>
    );
  }
  if (relation === "outgoing") {
    return <span className={`${base} bg-white/5 text-ink-mist`}><IconUsers size={14} /> Заявка отправлена</span>;
  }
  return (
    <button onClick={() => add.mutate()} disabled={add.isPending} className={`${base} bg-accent-lime/15 text-accent-lime`}>
      <IconUsers size={14} /> {relation === "incoming" ? "Принять в друзья" : "Добавить в друзья"}
    </button>
  );
}
