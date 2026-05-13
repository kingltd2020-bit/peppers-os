import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell, PhoneHeader, PhoneTabs } from "@/components/peppers/AppShell";
import { Search, Receipt as ReceiptIcon, ChevronLeft } from "lucide-react";
import { fetchInvoices } from "@/lib/peppers-api";

export const Route = createFileRoute("/invoices")({
  head: () => ({
    meta: [
      { title: "חשבוניות — Peppers OS" },
      { name: "description", content: "רשימת חשבוניות ספקים" },
    ],
  }),
  component: InvoicesPage,
});

type Row = {
  invoice_id: string;
  supplier_id: string;
  supplier_name: string;
  invoice_number: string;
  invoice_date: string;
  amount: string;
  invoice_pdf: string;
  created_at: string;
};

function InvoicesPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchInvoices()
      .then((data) => setRows(data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Running total — current month
  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const thisMonthRows = rows.filter(
    (r) => r.invoice_date && String(r.invoice_date).startsWith(currentMonth)
  );
  const monthTotal = thisMonthRows.reduce(
    (sum, r) => sum + (parseFloat(r.amount) || 0),
    0
  );
  const formattedTotal = monthTotal.toLocaleString("he-IL", {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 0,
  });

  return (
    <AppShell title="חשבוניות" subtitle="רשימת חשבוניות ספקים" phone>
      <PhoneHeader title="חשבוניות" trailing={<Search className="size-4" />} />

      {/* ── Monthly Counter ── */}
      <div className="px-5 pb-4 pt-2">
        <div className="rounded-2xl bg-primary/10 border border-primary/20 p-4 text-center">
          <div className="text-xs text-muted-foreground mb-1">רכש החודש הנוכחי</div>
          <div className="text-3xl font-bold text-primary tabular-nums">{formattedTotal}</div>
          <div className="mt-2 flex items-center justify-center gap-3 text-xs text-muted-foreground">
            <span><span className="font-semibold text-foreground">{thisMonthRows.length}</span> חשבוניות החודש</span>
            <span className="h-3 w-px bg-border" />
            <span><span className="font-semibold text-foreground">{rows.length}</span> סה"כ</span>
          </div>
        </div>
      </div>

      {/* ── States ── */}
      {loading && (
        <div className="px-5 py-8 text-center text-sm text-muted-foreground">
          טוען חשבוניות…
        </div>
      )}
      {error && (
        <div className="px-5 py-4 text-center text-sm text-destructive">
          שגיאה: {error}
        </div>
      )}
      {!loading && !error && rows.length === 0 && (
        <div className="px-5 py-8 text-center text-sm text-muted-foreground">
          אין חשבוניות להצגה
        </div>
      )}

      {/* ── Invoice List ── */}
      <ul className="space-y-2 px-3 pb-4">
        {rows.map((r) => {
          const dateStr = r.invoice_date ? String(r.invoice_date).slice(0, 10) : "";
          const amountNum = parseFloat(r.amount) || 0;
          const amountStr = amountNum
            ? `₪${amountNum.toLocaleString("he-IL")}`
            : "—";
          const supplierLabel = r.supplier_name && r.supplier_name !== r.supplier_id
            ? r.supplier_name
            : r.supplier_id;

          return (
            <li
              key={r.invoice_id}
              className="flex items-center gap-3 rounded-2xl border border-border bg-surface-1 p-3"
            >
              <div className="grid size-9 flex-shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                <ReceiptIcon className="size-4" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold truncate">{supplierLabel}</span>
                  {r.invoice_number && (
                    <span className="text-[10px] text-muted-foreground shrink-0">
                      #{r.invoice_number}
                    </span>
                  )}
                </div>
                <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>{dateStr}</span>
                  <span className="text-sm font-bold text-foreground tabular-nums">
                    {amountStr}
                  </span>
                </div>
                {r.invoice_pdf && (
                  <a
                    href={`https://drive.google.com/drive/search?q=${encodeURIComponent(r.invoice_id)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-block text-[10px] text-primary underline-offset-2 hover:underline"
                  >
                    צפה ב-Drive ↗
                  </a>
                )}
              </div>

              <ChevronLeft className="size-4 shrink-0 text-muted-foreground" />
            </li>
          );
        })}
      </ul>

      <PhoneTabs active="docs" />
    </AppShell>
  );
}
