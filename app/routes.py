"""Routen: Query-Parameter lesen, Daten laden, Template rendern."""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from urllib.parse import quote, urlencode

from app import data, table
from app.nav import NAV_ITEMS, SETTINGS_ITEM
from app.render import render

DEFAULT_SORT = "confidence"
DEFAULT_DIR = "asc"


def _sort_dir(query: dict[str, str]) -> tuple[str, str]:
    sort = query.get("sort", DEFAULT_SORT)
    if sort not in {"document", "date", "order", "confidence"}:
        sort = DEFAULT_SORT
    direction = query.get("dir", DEFAULT_DIR)
    if direction not in {"asc", "desc"}:
        direction = DEFAULT_DIR
    return sort, direction


def _base_context(active_key: str, page_title: str) -> dict:
    return {
        "nav_items": NAV_ITEMS,
        "settings_item": SETTINGS_ITEM,
        "active_key": active_key,
        "page_title": page_title,
    }


def dashboard(query: dict[str, str]) -> str:
    all_items, warning = data.get_open_review_items()
    kpis = data.compute_kpis(all_items)
    today = data.compute_today(all_items)
    max_today = max(today.values()) if any(today.values()) else 0

    sort, direction = _sort_dir(query)
    review_items = [i for i in all_items if i.bucket in ("pruefung", "nicht_zuordenbar")]
    review_items = data.sort_items(review_items, sort, direction)[:8]
    cols = table.build_sort_columns("/", query, sort, direction)

    all_rows, _ = data.get_assignment_rows()
    recent_events = sorted(data.order_events(all_rows), key=lambda e: e[0], reverse=True)[:8]

    context = _base_context("uebersicht", "Übersicht")
    context.update(
        warning=warning,
        kpis=kpis,
        today=today,
        max_today=max_today,
        items=review_items,
        cols=cols,
        recent_events=recent_events,
    )
    return render("dashboard.html", **context)


_EMPTY_MESSAGES = {
    "pruefung": "Keine Dokumente mit Prüfbedarf. Alle offenen Fälle sind entweder eindeutig oder bereits bestätigt.",
    "nicht_zuordenbar": "Keine nicht zuordenbaren Dokumente.",
    "bestaetigt": "Noch keine bestätigten Zuordnungen.",
}


def _empty_message(active_filter: str | None, search_query: str | None) -> str:
    if search_query:
        return f"Keine Treffer für „{search_query}“."
    if active_filter in _EMPTY_MESSAGES:
        return _EMPTY_MESSAGES[active_filter]
    return "Keine offenen Zuordnungen. Alle aktuell importierten Dokumente wurden geprüft."


def zuordnungen(query: dict[str, str]) -> str:
    all_rows, warning = data.get_assignment_rows()
    open_count = sum(1 for r in all_rows if r.status != "Bestätigt")

    active_filter = query.get("filter") or None
    if active_filter not in {"pruefung", "nicht_zuordenbar", "bestaetigt"}:
        active_filter = None
    search_query = query.get("q") or None
    filtered = data.filter_assignment_rows(all_rows, active_filter, search_query)

    sort, direction = _sort_dir(query)
    if "sort" in query:
        filtered = data.sort_assignment_rows(filtered, sort, direction)
    else:
        # Standardansicht: offene/unsichere Fälle zuerst, dringendste zuerst.
        filtered = data.sort_assignment_rows(filtered, sort, direction, prioritize_open=True)
    cols = table.build_sort_columns("/zuordnungen", query, sort, direction)

    context = _base_context("zuordnungen", "Zuordnungen")
    context.update(
        warning=warning,
        rows=filtered,
        cols=cols,
        open_count=open_count,
        active_filter=active_filter,
        search_query=search_query,
        empty_message=_empty_message(active_filter, search_query),
    )
    return render("zuordnungen.html", **context)


def pruefen(query: dict[str, str]) -> str:
    doc_path = query.get("doc")
    detail = data.get_review_detail(doc_path) if doc_path else None

    if detail is None:
        context = _base_context("zuordnungen", "Zuordnung prüfen")
        context.update(
            message="Dokument wurde nicht gefunden (evtl. verschoben oder gelöscht).",
        )
        return render("placeholder.html", **context)

    item, candidate, reasons, confirmed = detail

    manual_q = query.get("manual_q")
    manual_results: list = []
    if manual_q and candidate is None and confirmed is None:
        manual_results, _ = data.search_orders(manual_q)

    context = _base_context("zuordnungen", "Zuordnung prüfen")
    context.update(
        item=item,
        candidate=candidate,
        reasons=reasons,
        confirmed=confirmed,
        error=query.get("error"),
        manual_q=manual_q,
        manual_results=manual_results,
    )
    return render("pruefen.html", **context)


def confirm(form: dict[str, str]) -> str:
    """Verarbeitet den POST von 'Zuordnung bestätigen' und leitet zurück."""
    doc_path = form.get("doc", "")
    erf_nr = form.get("erf_nr", "")
    document_type = form.get("document_type") or None

    try:
        score = float(form.get("score", "0"))
    except ValueError:
        score = 0.0

    if not doc_path or not erf_nr:
        redirect_target = f"/zuordnung/pruefen?doc={quote(doc_path)}&error={quote('Unvollständige Anfrage.')}"
        return redirect_target

    ok, message = data.confirm_assignment(doc_path, erf_nr, score, document_type)

    if ok:
        return f"/zuordnung/pruefen?doc={quote(doc_path)}"
    return f"/zuordnung/pruefen?doc={quote(doc_path)}&error={quote(message)}"


def eingang(query: dict[str, str]) -> str:
    records, warning = data.get_assignment_rows()
    status = data.compute_import_status(records)

    sort = query.get("sort", "date")
    if sort not in {"document", "date", "status"}:
        sort = "date"
    direction = query.get("dir", "desc")
    if direction not in {"asc", "desc"}:
        direction = "desc"

    records = data.sort_assignment_rows(records, sort, direction)
    cols = table.build_sort_columns("/eingang", query, sort, direction, table.IMPORT_SORTABLE_COLUMNS)

    context = _base_context("eingang", "Eingang")
    context.update(
        warning=warning,
        records=records,
        cols=cols,
        status=status,
    )
    return render("eingang.html", **context)


def upload(filename: str, content: bytes) -> dict:
    """Verarbeitet einen Datei-Upload synchron und gibt das Ergebnis als Dict zurück."""
    saved_path, error = data.save_uploaded_pdf(filename, content)
    if error:
        return {"ok": False, "filename": filename, "error": error}

    # Sofort verarbeiten (Extraktion + Matching), damit die Rückmeldung
    # einen echten Status zeigt statt "hochgeladen, Status unbekannt".
    item, _candidate, _reasons, _confirmed = data.get_review_detail(str(saved_path))
    status_label = data.workflow_status(item.candidate_erf_nr, item.note)

    return {
        "ok": True,
        "filename": saved_path.name,
        "status": status_label,
        "confidence": round(item.confidence * 100),
    }


ORDER_PAGE_SIZE = 20

_ORDER_EMPTY_MESSAGES = {
    "Vollständig": "Keine vollständig zugeordneten Aufträge.",
    "Prüfung erforderlich": "Keine Aufträge mit offenem Prüfbedarf.",
    "Ohne Dokumente": "Keine Aufträge ohne Dokumente.",
}


def _order_empty_message(status_filter: str | None, search_query: str | None) -> str:
    if search_query:
        return f"Keine Treffer für „{search_query}“."
    if status_filter in _ORDER_EMPTY_MESSAGES:
        return _ORDER_EMPTY_MESSAGES[status_filter]
    return "Noch keine Aufträge in der Datenbank."


def _order_date_param(query: dict[str, str], key: str):
    value = query.get(key)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def auftraege(query: dict[str, str]) -> str:
    all_summaries, warning = data.get_order_summaries()

    status_filter = query.get("status") or None
    if status_filter not in data.ORDER_STATUS_CLASS:
        status_filter = None
    kunde_filter = query.get("kunde") or None
    search_query = query.get("q") or None
    date_from = _order_date_param(query, "von")
    date_to = _order_date_param(query, "bis")

    filtered = data.filter_order_summaries(
        all_summaries, status_filter, kunde_filter, date_from, date_to, search_query
    )

    sort = query.get("sort", "datum")
    if sort not in data.ORDER_SORT_FIELDS:
        sort = "datum"
    direction = query.get("dir", "desc")
    if direction not in {"asc", "desc"}:
        direction = "desc"
    filtered = data.sort_order_summaries(filtered, sort, direction)

    try:
        page = max(1, int(query.get("page", "1")))
    except ValueError:
        page = 1
    total = len(filtered)
    total_pages = max(1, (total + ORDER_PAGE_SIZE - 1) // ORDER_PAGE_SIZE)
    page = min(page, total_pages)
    page_items = filtered[(page - 1) * ORDER_PAGE_SIZE : page * ORDER_PAGE_SIZE]

    cols = table.build_sort_columns("/auftraege", query, sort, direction, table.ORDER_SORTABLE_COLUMNS)
    page_links = table.build_page_links("/auftraege", query, total_pages, page)
    kunden_options = sorted({s.order.kunde for s in all_summaries if s.order.kunde})

    context = _base_context("auftraege", "Aufträge")
    context.update(
        warning=warning,
        summaries=page_items,
        cols=cols,
        status_filter=status_filter,
        kunde_filter=kunde_filter,
        search_query=search_query,
        von=query.get("von", ""),
        bis=query.get("bis", ""),
        kunden_options=kunden_options,
        total=total,
        page_links=page_links,
        show_pagination=total_pages > 1,
        empty_message=_order_empty_message(status_filter, search_query),
    )
    return render("auftraege.html", **context)


def auftrag_details(query: dict[str, str]) -> str:
    erf_nr = query.get("erf_nr")
    summary, warning = data.get_order_detail(erf_nr) if erf_nr else (None, None)

    if summary is None:
        context = _base_context("auftraege", "Auftrag")
        context.update(message=f"Auftrag {erf_nr or ''} wurde nicht gefunden.".strip())
        return render("placeholder.html", **context)

    events = data.order_events(summary.documents)

    context = _base_context("auftraege", f"Auftrag {summary.order.erf_nr}")
    context.update(warning=warning, summary=summary, events=events)
    return render("auftrag_details.html", **context)


DOCUMENT_PAGE_SIZE = 20

_DOCUMENT_EMPTY_MESSAGES = {
    "zugeordnet": "Keine zugeordneten Dokumente.",
    "pruefung": "Keine Dokumente mit Prüfbedarf.",
    "nicht_zuordenbar": "Keine nicht zuordenbaren Dokumente.",
}


def _document_empty_message(status_filter: str | None, search_query: str | None) -> str:
    if search_query:
        return f"Keine Treffer für „{search_query}“."
    if status_filter in _DOCUMENT_EMPTY_MESSAGES:
        return _DOCUMENT_EMPTY_MESSAGES[status_filter]
    return "Noch keine Dokumente importiert."


def _document_href(query: dict[str, str], doc_path: str | None) -> str:
    """Baut einen /dokumente-Link, der die aktuellen Filter/Sortierung/Seite
    beibehält und nur den `doc`-Parameter setzt (oder entfernt)."""
    params = {k: v for k, v in query.items() if k != "doc"}
    if doc_path:
        params["doc"] = doc_path
    return f"/dokumente?{urlencode(params)}" if params else "/dokumente"


def dokumente(query: dict[str, str]) -> str:
    all_entries, warning = data.get_document_entries()
    status_counts = data.compute_document_status_counts(all_entries)

    status_filter = query.get("status") or None
    if status_filter not in ("zugeordnet", "pruefung", "nicht_zuordenbar"):
        status_filter = None
    doc_type_filter = query.get("typ") or None
    search_query = query.get("q") or None
    date_from = _order_date_param(query, "von")
    date_to = _order_date_param(query, "bis")

    filtered = data.filter_document_entries(
        all_entries, status_filter, doc_type_filter, date_from, date_to, search_query
    )

    sort = query.get("sort", "datum")
    if sort not in data.DOCUMENT_SORT_FIELDS:
        sort = "datum"
    direction = query.get("dir", "desc")
    if direction not in {"asc", "desc"}:
        direction = "desc"
    filtered = data.sort_document_entries(filtered, sort, direction)

    try:
        page = max(1, int(query.get("page", "1")))
    except ValueError:
        page = 1
    total = len(filtered)
    total_pages = max(1, (total + DOCUMENT_PAGE_SIZE - 1) // DOCUMENT_PAGE_SIZE)
    page = min(page, total_pages)
    page_items = filtered[(page - 1) * DOCUMENT_PAGE_SIZE : page * DOCUMENT_PAGE_SIZE]

    cols = table.build_sort_columns("/dokumente", query, sort, direction, table.DOCUMENT_SORTABLE_COLUMNS)
    page_links = table.build_page_links("/dokumente", query, total_pages, page)
    doc_type_options = sorted({e.row.document_type_label for e in all_entries})

    selected_path = query.get("doc")
    view_rows = [
        {"entry": e, "href": _document_href(query, e.row.path), "selected": e.row.path == selected_path}
        for e in page_items
    ]

    selected_entry = None
    events = []
    selected_order_number = None
    selected_file_size = None
    if selected_path:
        selected_entry, _w = data.get_document_entry(selected_path)
        if selected_entry:
            events = data.order_events([selected_entry.row])
            selected_order_number, selected_file_size = data.get_document_file_info(selected_path)

    context = _base_context("dokumente", "Dokumente")
    context.update(
        warning=warning,
        status_counts=status_counts,
        status_filter=status_filter,
        doc_type_filter=doc_type_filter,
        doc_type_options=doc_type_options,
        search_query=search_query,
        von=query.get("von", ""),
        bis=query.get("bis", ""),
        cols=cols,
        view_rows=view_rows,
        page_links=page_links,
        show_pagination=total_pages > 1,
        empty_message=_document_empty_message(status_filter, search_query),
        selected_entry=selected_entry,
        selected_order_number=selected_order_number,
        selected_file_size=selected_file_size,
        close_href=_document_href(query, None),
        events=events,
    )
    return render("dokumente.html", **context)


_RANGE_PRESETS = {"7": 7, "30": 30, "90": 90, "365": 365}
_RANGE_LABELS = {"7": "Letzte 7 Tage", "30": "Letzte 30 Tage", "90": "Letzte 90 Tage", "365": "Letzte 12 Monate", "alle": "Gesamter Zeitraum"}


def _auswertungen_range(query: dict[str, str]) -> tuple[date | None, date | None, str]:
    range_key = query.get("range", "30")
    if range_key == "alle":
        return None, None, "alle"
    if range_key not in _RANGE_PRESETS:
        range_key = "30"
    date_to = date.today()
    date_from = date_to - timedelta(days=_RANGE_PRESETS[range_key])
    return date_from, date_to, range_key


def _build_trend_bars(trend: list[dict]) -> list[dict]:
    """Balken-Koordinaten in einem 0–100-Koordinatensystem (SVG viewBox),
    damit die Grafik unabhängig von der tatsächlichen Pixelbreite skaliert."""
    if not trend:
        return []
    n = len(trend)
    gap = 2.0
    bar_width = (100 - gap * (n - 1)) / n if n > 1 else 100.0
    bars = []
    x = 0.0
    for point in trend:
        bar_height = max(3.0, point["quote"] * 40)
        bars.append(
            {
                "x": round(x, 2),
                "y": round(40 - bar_height, 2),
                "width": round(bar_width, 2),
                "height": round(bar_height, 2),
                "label": point["label"],
                "pct": round(point["quote"] * 100),
            }
        )
        x += bar_width + gap
    return bars


def auswertungen(query: dict[str, str]) -> str:
    all_stats, warning = data.get_dokument_stats()
    date_from, date_to, range_key = _auswertungen_range(query)
    stats = data.filter_dokument_stats(all_stats, date_from, date_to)

    kpis = data.compute_auswertungen_kpis(stats)
    confidence = data.compute_confidence_distribution(stats, data.get_high_confidence_threshold())
    trend = data.compute_quality_trend(stats)
    trend_bars = _build_trend_bars(trend) if len(trend) >= 2 else []

    context = _base_context("auswertungen", "Auswertungen")
    context.update(
        warning=warning,
        kpis=kpis,
        confidence=confidence,
        trend_bars=trend_bars,
        range_key=range_key,
        range_label=_RANGE_LABELS.get(range_key, "Letzte 30 Tage"),
        range_options=[("7", _RANGE_LABELS["7"]), ("30", _RANGE_LABELS["30"]), ("90", _RANGE_LABELS["90"]), ("365", _RANGE_LABELS["365"]), ("alle", _RANGE_LABELS["alle"])],
        has_any_data=len(all_stats) > 0,
        has_range_data=len(stats) > 0,
    )
    return render("auswertungen.html", **context)


def export_csv(query: dict[str, str]) -> str:
    """Kleine CSV-Exportfunktion: exportiert genau die im Zeitraum
    gefilterten Dokumente-Zeilen, deutschsprachig formatiert."""
    all_stats, _warning = data.get_dokument_stats()
    date_from, date_to, _range_key = _auswertungen_range(query)
    stats = data.filter_dokument_stats(all_stats, date_from, date_to)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        ["Dateiname", "Status", "Sicherheit (%)", "Belegdatum", "Betrag", "Währung", "Auftrag", "Importiert am"]
    )
    for s in stats:
        writer.writerow(
            [
                s.filename,
                s.status,
                round(s.score * 100) if s.score is not None else "",
                s.belegdatum.strftime("%d.%m.%Y") if s.belegdatum else "",
                str(s.betrag).replace(".", ",") if s.betrag is not None else "",
                s.waehrung or "",
                s.erf_nr or "",
                s.imported_at.strftime("%d.%m.%Y %H:%M"),
            ]
        )
    return buffer.getvalue()


def einstellungen(query: dict[str, str]) -> str:
    tab = query.get("tab", "datenquellen")
    if tab not in ("datenquellen", "verarbeitung", "matching"):
        tab = "datenquellen"

    einstellungen_row, warning = data.get_einstellungen()
    datasources = data.get_datasources()

    context = _base_context("einstellungen", "Einstellungen")
    context.update(
        warning=warning,
        tab=tab,
        einstellungen=einstellungen_row,
        datasources=datasources,
        conn_ok=query.get("conn_ok"),
        conn_msg=query.get("conn_msg"),
        saved=query.get("saved") == "1",
        save_error=query.get("save_error"),
    )
    return render("einstellungen.html", **context)


def einstellungen_verbindung_pruefen() -> str:
    ok, msg = data.check_database_connection()
    return f"/einstellungen?tab=datenquellen&conn_ok={'1' if ok else '0'}&conn_msg={quote(msg)}"


def einstellungen_verarbeitung_speichern(form: dict[str, str]) -> str:
    ocr_aktiv = "ocr_aktiv" in form
    matching_aktiv = "matching_aktiv" in form
    ok, msg = data.update_verarbeitung(ocr_aktiv, matching_aktiv)
    if ok:
        return "/einstellungen?tab=verarbeitung&saved=1"
    return f"/einstellungen?tab=verarbeitung&save_error={quote(msg)}"


def einstellungen_matching_speichern(form: dict[str, str]) -> str:
    raw = form.get("schwelle", "")
    try:
        schwelle = int(raw)
    except ValueError:
        return f"/einstellungen?tab=matching&save_error={quote('Bitte eine ganze Zahl zwischen 0 und 100 eingeben.')}"
    ok, msg = data.update_matching_schwelle(schwelle)
    if ok:
        return "/einstellungen?tab=matching&saved=1"
    return f"/einstellungen?tab=matching&save_error={quote(msg)}"


def einstellungen_ordner_speichern(form: dict[str, str]) -> str:
    ok, msg = data.update_scan_ordner(form.get("scan_ordner", ""))
    if ok:
        return "/einstellungen?tab=datenquellen&saved=1"
    return f"/einstellungen?tab=datenquellen&save_error={quote(msg)}"
