import { api } from "@/lib/api";
import type { StarsInvoiceCreate, StarsInvoiceStatus, WheelSpinResult, WheelStatus } from "@/types";

export async function fetchWheelStatus(): Promise<WheelStatus> {
  const { data } = await api.get<WheelStatus>("/wheel/status");
  return data;
}

export async function spinFree(): Promise<WheelSpinResult> {
  const { data } = await api.post<WheelSpinResult>("/wheel/spin/free");
  return data;
}

export async function spinPaidCoins(): Promise<WheelSpinResult> {
  const { data } = await api.post<WheelSpinResult>("/wheel/spin/coins");
  return data;
}

export async function createWheelStarsInvoice(): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/wheel/spin/stars-invoice");
  return data;
}

export async function fetchWheelStarsInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/wheel/stars-invoices/${payloadToken}`);
  return data;
}
