import { api } from "@/lib/api";

export type ShareKind = "card" | "match" | "trophy" | "my_player";

export interface SharePrepared {
  /** Telegram prepared inline message (send with WebApp.shareMessage); null in dev / on failure. */
  prepared_message_id: string | null;
  image_url: string;
  caption: string;
  link: string;
  /** t.me/share/url fallback with the same caption and referral link. */
  share_url: string;
}

export async function prepareShare(kind: ShareKind, id: number): Promise<SharePrepared> {
  const { data } = await api.post<SharePrepared>("/share/prepare", { kind, id });
  return data;
}
