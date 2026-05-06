import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell, PhoneHeader, PhoneTabs, SoftChip } from "@/components/peppers/AppShell";
import { Search, ShoppingBag, AlertTriangle, Receipt as ReceiptIcon, Box, ChevronLeft } from "lucide-react";
import { fetchInvoices } from "@/lib/peppers-api";

export const Route = createFileRoute("/invoices")({
  head: () => ({
    meta: [
      { title: "חשבוניות · Peppers OS" },
      { name: "description", content: "מסמכים ורשימת חשבוניות עם סטטוסים מהשטח" },
      { property: "og:title", content: "חשבוניות · Peppers OS" },
      { property: "og:description", content: "ניהול חשבוניות ספקים וסנכרון ל-Comax" },
    ],
  }),
  component: InvoicesPage,
});

type Row = {
  doc_id: string;
  supplier_name: string;
  supplier_id: string;
  document_date: string;
  amount_total: string;
  document_type: string;
  drive_url: string;
  file_name: string;
};

const DOC_TYPE_LABELS: Record<string, { label: string; variant: "primary" | "warning" | "danger" | "neutral" }> = {
  supplier_invoice:    { label: "חשבונית ספק",    variant: "warning" },
  delivery_note:       { label: "תעודת משלוח",    variant: "neutral" },
  credit_note:         { label: "זיכוי",           variant: "primary" },
  correction_invoice:  { label: "חשבונית תיקון",  variant: "warning" },
  service_invoice:     { label: "חשבונית שירות",  variant: "neutral" },
  outgoing_invoice:    { label: "חשבונית יוצאת",  variant: "primary" },
  unknown:             { label: "לא מסווג",        variant: "danger"  },
};

function docTypeChip(docType: string) {
  const meta = DOC_TYPE_LABELS[docType] ?? { label: docType || "—", variant: "neutral" as const };
  return <SoftChip variant={meta.variant}>{meta.label}</SoftChip>;
}

function rowIcon(docType: string) {
  if (docType === "unknown")
    return (
      <div className="grid size-9 place-items-center rounded-lg bg-destructive-soft text-destructive">
        <AlertTriangle className="size-4" />
      </div>
    );
  return (
    <div className="grid size-9 place-items-center rounded-lg bg-primary-soft text-primary">
      <ReceiptIcon className="size-4" />
    </div>
  );
}

function InvoicesPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchInvoices()
      .then((data) => setRows(data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell title="חשבוניות" subtitle="מסמכים · רשימת ספקים" phone>
      <PhoneHeader title="פלפלים" trailing={<Search className="size-4" />} />

      <div className="px-5 pb-3">
        <div className="text-center">
          <div className="text-xs text-muted-foreground">רשימה / מסמכים</div>
          <div className="mt-2 inline-flex items-center gap-3 rounded-xl bg-surface-2 px-4 py-2 text-xs">
            <div className="text-foreground/80">
              <span className="font-bold">12</span> פתוחות
            </div>
            <span className="h-3 w-px bg-border" />
            <div className="text-foreground/80">
              <span className="font-bold">124</span> סה״כ
            </div>
          </div>
        </div>
      </div>

      {loading && (
        <div className="px-5 py-8 text-center text-sm text-muted-foreground">טוען חשבוניות…</div>
      )}

      {!loading && rows.length === 0 && (
        <div className="px-5 py-8 text-center text-sm text-muted-foreground">אין חשבוניות זמינות</div>
      )}

      <ul className="space-y-2 px-3 pb-4">
        {rows.map((r) => (
          <li
            key={r.doc_id}
            className="flex items-center gap-3 rounded-2xl border border-border bg-surface-1 p-3"
          >
            {rowIcon(r.document_type)}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold truncate">{r.supplier_name}</span>
                {docTypeChip(r.document_type)}
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                <span>{r.document_date}</span>
                <span className="text-sm font-bold text-foreground tabular-nums">
                  {r.amount_total ? `₪${r.amount_total}` : "—"}
                </span>
              </div>
              {r.drive_url && (
                <a
                  href={r.drive_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 text-[10px] text-primary underline-offset-2 hover:underline"
                >
                  פתח ב-Drive
                </a>
              )}
            </div>
            <ChevronLeft className="size-4 text-muted-foreground" />
          </li>
        ))}
      </ul>

      <div className="flex justify-center pb-4">
        <button className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/30">
          <Box className="size-4" /> סרוק חשבונית
          <ShoppingBag className="size-4" />
        </button>
      </div>

      <PhoneTabs active="docs" />
    </AppShell>
  );
}
