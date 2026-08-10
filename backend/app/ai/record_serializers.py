"""Shared record payload builders used by local and tool-backed AI reads."""
from collections import defaultdict

from sqlalchemy import select

from app.models import Client, SaleLine


def sale_invoice_context(db, user, invoices) -> dict:
    invoices = list(invoices)
    invoice_ids = {row.id for row in invoices}
    client_ids = {row.client_id for row in invoices if row.client_id}
    clients = {}
    if client_ids:
        rows = db.execute(select(Client).where(
            Client.organization_id == user.organization_id,
            Client.id.in_(client_ids),
        )).scalars()
        clients = {row.id: row for row in rows}

    lines = defaultdict(list)
    if invoice_ids:
        rows = db.execute(select(SaleLine).where(
            SaleLine.organization_id == user.organization_id,
            SaleLine.invoice_id.in_(invoice_ids),
        ).order_by(SaleLine.invoice_id, SaleLine.display_order, SaleLine.id)).scalars()
        for row in rows:
            lines[row.invoice_id].append(row)
    return {"clients": clients, "sale_lines": lines}


def serialize_sale_invoice(invoice, context: dict | None = None) -> dict:
    context = context or {"clients": {}, "sale_lines": {}}
    client = context.get("clients", {}).get(invoice.client_id)
    customer_name = (
        f"{client.first_name} {client.last_name}".strip()
        if client else "Walk-in customer"
    )
    lines = list(context.get("sale_lines", {}).get(invoice.id, []))
    item_names = [line.item_name for line in lines[:3]]
    pending_paise = max(int(invoice.total_paise or 0) - int(invoice.paid_paise or 0), 0)
    return {
        "id": invoice.id,
        "kind": "invoice",
        "display_name": invoice.invoice_number,
        "display_meta": customer_name,
        "invoice_number": invoice.invoice_number,
        "customer_name": customer_name,
        "item_names": item_names,
        "item_count": len(lines),
        "status": invoice.status,
        "total_paise": invoice.total_paise,
        "paid_paise": invoice.paid_paise,
        "pending_paise": pending_paise,
        "created_at": invoice.created_at,
        "client_id": invoice.client_id,
        "profile_ref": {"kind": "invoice", "id": invoice.id},
    }
