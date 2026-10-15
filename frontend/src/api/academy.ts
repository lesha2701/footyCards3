import { api } from "@/lib/api";
import type { AcademyState, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchAcademy(): Promise<AcademyState> {
  const { data } = await api.get<AcademyState>("/academy");
  return data;
}

export async function upgradeAcademyWing(code: string, idempotencyKey: string): Promise<AcademyState> {
  const { data } = await api.post<AcademyState>(`/academy/wings/${code}/upgrade`, { idempotency_key: idempotencyKey });
  return data;
}

export async function claimScoutReport(idempotencyKey: string): Promise<AcademyState> {
  const { data } = await api.post<AcademyState>("/academy/scout-report", { idempotency_key: idempotencyKey });
  return data;
}

export async function createAcademySpeedupInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/academy/speedup-invoice");
  return data;
}

export async function fetchAcademyInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/academy/stars-invoices/${payloadToken}`);
  return data;
}
