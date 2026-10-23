import TransactionsTable from "@/admin/components/TransactionsTable";

export default function AdminTransactionsPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold">Транзакции</h1>
      <p className="text-xs text-slate-400">Все движения монет всех игроков — по страницам, новые сверху.</p>
      <TransactionsTable />
    </div>
  );
}
