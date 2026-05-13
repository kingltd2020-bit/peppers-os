const SHEETS_URL = "https://script.google.com/macros/s/AKfycbwq-Q_uMeb5jYJV61go9VMBsnnWjH1NcemdHLNOgxUB6Tr1OajjNxSlwocgrhwXMk6Q/exec";

export async function fetchInvoices() {
  const res = await fetch(`${SHEETS_URL}?sheet=Supplier_Invoices`);
  const data = await res.json();
  return data.rows || [];
}

export async function fetchSuppliers() {
  const res = await fetch(`${SHEETS_URL}?sheet=Suppliers`);
  const data = await res.json();
  return data.rows || [];
}

export async function fetchPromotions(): Promise<PromotionRow[]> {
  const res = await fetch(`${SHEETS_URL}?sheet=Promotions`);
  const data = await res.json();
  return data.rows || [];
}

export type PromotionRow = {
  barcode: string;
  product_name?: string;
  discount: string;
  start_date: string;
  end_date: string;
  notes?: string;
  submitted_at?: string;
};

export async function submitPromotion(form: {
  barcode: string;
  discount: string;
  startDate: string;
  endDate: string;
  notes: string;
}): Promise<void> {
  const res = await fetch(SHEETS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "appendRow",
      sheet: "Promotions",
      row: {
        barcode: form.barcode,
        discount: form.discount,
        start_date: form.startDate,
        end_date: form.endDate,
        notes: form.notes,
        submitted_at: new Date().toISOString(),
      },
    }),
  });
  if (!res.ok) throw new Error(`Sheets API ${res.status}`);
}

export const PEPPERS_WEBHOOK_URL = SHEETS_URL;
