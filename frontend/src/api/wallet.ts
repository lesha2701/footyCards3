import { api } from "@/lib/api";
import type { CoinPackage, StarsInvoiceCreate, StarsInvoiceStatus } from "@/types";

export async function fetchCoinPackages(): Promise<CoinPackage[]> {
  const { data } = await api.get<CoinPackage[]>("/wallet/coin-packages");
  return data;
}

export async function createCoinInvoice(coinPackageId: number): Promise<StarsInvoiceCreate> {
  const { data } = await api.post<StarsInvoiceCreate>("/wallet/stars-invoice", { coin_package_id: coinPackageId });
  return data;
}

export async function fetchCoinInvoiceStatus(payloadToken: string): Promise<StarsInvoiceStatus> {
  const { data } = await api.get<StarsInvoiceStatus>(`/wallet/stars-invoices/${payloadToken}`);
  return data;
}
