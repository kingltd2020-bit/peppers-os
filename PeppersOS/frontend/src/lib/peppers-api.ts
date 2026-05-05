const SHEETS_URL = "https://script.google.com/macros/s/AKfycbzlivt_2ofBDDtNLltqmIkHUhtdGaXl6IFpxIL5hnP9gngluI0QoyvlOwcJe0E8scfC/exec";

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

export const PEPPERS_WEBHOOK_URL = SHEETS_URL;
