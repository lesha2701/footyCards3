import { api } from "@/lib/api";

export interface FreeStarsDelivery {
  recipient_id: number;
  recipient_name: string;
  stars: number;
}

/** Admin only: deliver a pending Stars invoice without paying — to the admin,
 * or to `recipient` (id, Telegram id or @username) as a gift. */
export async function freeStarsDelivery(payloadToken: string, recipient: string | null): Promise<FreeStarsDelivery> {
  const { data } = await api.post<FreeStarsDelivery>(`/admin/stars-purchases/free/${payloadToken}`, { recipient });
  return data;
}
