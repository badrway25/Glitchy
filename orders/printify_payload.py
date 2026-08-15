COUNTRY_NAME_TO_ISO2 = {
    "italy": "IT",
    "italia": "IT",
    "belgium": "BE",
    "belgio": "BE",
    "france": "FR",
    "germany": "DE",
    "spain": "ES",
    "netherlands": "NL",
    # aggiungi quelli che ti servono
}

def _country_iso2(value: str) -> str:
    if not value:
        return ""
    v = value.strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    return COUNTRY_NAME_TO_ISO2.get(v.lower(), v)  # fallback: manda com'è


def _pick_printify_variant_id(order_product):
    vids = []
    for v in order_product.variations.all():
        pid = getattr(v, "printify_variant_id", None)
        if pid:
            vids.append(str(pid))

    vids = list(dict.fromkeys(vids))  # unique

    if len(vids) == 1:
        return vids[0]
    if len(vids) == 0:
        raise ValueError(
            f"Missing printify_variant_id for '{order_product.product.product_name}' "
            f"(OrderProduct id={order_product.id})."
        )
    raise ValueError(
        f"Multiple printify_variant_id found for '{order_product.product.product_name}' "
        f"(OrderProduct id={order_product.id}): {vids}. "
        f"You must have exactly ONE Printify variant id for the selected combo."
    )


def build_printify_payload(*, order, order_products):
    address_to = {
        "first_name": order.first_name,
        "last_name": order.last_name,
        "email": order.email,
        "phone": order.phone,
        "country": (order.country or "IT").upper(),     # ISO2
        "region": order.state or "",
        "address1": order.address_line_1,
        "address2": order.address_line_2 or "",
        "city": order.city,
        "zip": getattr(order, "postal_code", "") or "",
    }

    line_items = []
    for op in order_products:
        p = op.product
        if not getattr(p, "printify_product_id", None):
            raise ValueError(f"Missing printify_product_id for product '{p.product_name}' (id={p.id}).")

        variant_id = _pick_printify_variant_id(op)

        line_items.append({
            "product_id": str(p.printify_product_id),
            "variant_id": int(variant_id) if str(variant_id).isdigit() else variant_id,
            "quantity": int(op.quantity),
        })

    from shipping.express import is_express, shipping_method_id

    method = getattr(order, "shipping_method", "") or "standard"
    payload = {
        "external_id": str(order.order_number),
        "label": f"Order {order.order_number}",
        "line_items": line_items,
        # Printify's integer vocabulary: 1 standard · 2 priority · 3 express · 4 economy.
        # Previously absent, so Printify silently defaulted every order to standard even
        # when the customer paid for something faster.
        "shipping_method": shipping_method_id(method),
        "send_shipping_notification": True,
        "address_to": address_to,
    }
    if is_express(method):
        # The express endpoint requires both contact fields on address_to; refuse
        # to submit rather than have Printify reject (or silently downgrade) an
        # order the customer already paid Express for.
        missing = [f for f in ("email", "phone") if not str(address_to.get(f) or "").strip()]
        if missing:
            raise ValueError(
                "Printify Express requires address_to.%s" % " and address_to.".join(missing))
        payload["is_printify_express"] = True
    return payload
