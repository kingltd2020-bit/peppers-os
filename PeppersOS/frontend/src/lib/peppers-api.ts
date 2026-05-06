const SHEETS_URL = "https://script.google.com/macros/s/AKfycbwq-Q_uMeb5jYJV61go9VMBsnnWjH1NcemdHLNOgxUB6Tr1OajjNxSlwocgrhwXMk6Q/exec";

export async function fetchInvoices() {
  const res = await fetch(`${SHEETS_URL}?sheet=Documents_Master_MVP`);
  const data = await res.json();
  return data.rows || [];
}

export async function fetchSuppliers() {
  const res = await fetch(`${SHEETS_URL}?sheet=Suppliers`);
  const data = await res.json();
  return data.rows || [];
}

export const PEPPERS_WEBHOOK_URL = SHEETS_URL;
