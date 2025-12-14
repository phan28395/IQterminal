from pathlib import Path

from rich.text import Text

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, ContentSwitcher, DataTable, Footer, Header, Input, Static, Tab, Tabs, Tree
from textual.screen import ModalScreen
from textual.binding import Binding

from sqlalchemy import select

from .config import load_config
from .data import dao
from .data.db import get_engine, get_session
from .data.models import Filing, Metric, Ticker
from .services.poller import Poller
from .services.ticker_loader import fetch_sec_tickers, load_sec_tickers_from_file


class FinancialTerminal(App[None]):
    """
    Textual entrypoint with a header/sidebar/tabs layout wired to the data layer.
    """

    BINDINGS = []

    def __init__(self) -> None:
        self.config = load_config()
        self.engine = get_engine(Path("financial_terminal.db"))
        self.session = get_session(self.engine)
        dao.init_db(self.session)
        self.filter_symbol: str | None = None
        super().__init__()

    CSS = """
    #sidebar {
        width: 36;
        min-width: 28;
    }
    #suggestions-panel {
        height: 12;
        layer: overlay;
        dock: top;
        offset: 0 5;
        width: 100%;
        background: $surface;
        border: tall $accent;
    }
    #suggestions-panel.hidden {
        display: none;
    }
    #search-suggestions {
        height: 10;
    }
    #notes {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("Watchlist", id="watchlist-title")
                yield Input(placeholder="Ticker (e.g., AAPL)", id="add-ticker-input")
                with Horizontal():
                    yield Button("Add", id="add-ticker-button")
                yield Button("Remove Selected", id="remove-ticker-button")
                with Vertical(id="suggestions-panel"):
                    yield Static("Suggestions", id="suggestions-title")
                    yield DataTable(id="search-suggestions")
                tree = Tree("Watchlist", id="watchlist-tree")
                tree.root.expand()
                yield tree
                yield Static("Add Note/File to selected ticker", id="note-helper")
                yield Input(placeholder="Note title", id="note-title")
                yield Input(placeholder="Attachment path or URL (optional)", id="note-attachment")
                yield Button("Add Note/File", id="add-note-button")
                yield Static("Status: Ready", id="status-bar")
            with Vertical(id="main"):
                yield Tabs(
                    Tab("Dashboard", id="tab-dashboard"),
                    Tab("Filings", id="tab-filings"),
                    Tab("Metrics", id="tab-metrics"),
                    Tab("Formulas", id="tab-formulas"),
                    Tab("Widgets", id="tab-widgets"),
                )
                with ContentSwitcher(initial="dashboard", id="content-switcher"):
                    yield Static("Dashboard coming soon", id="dashboard")
                    yield DataTable(id="filings-table")
                    yield DataTable(id="metrics-table")
                    yield DataTable(id="formulas-table")
                    yield DataTable(id="widgets-table")
        yield Footer()

    def on_mount(self) -> None:
        self._setup_tables()
        self._load_sec_tickers_if_needed()
        self.refresh_watchlist()
        self.refresh_filings_table()
        self.refresh_search_suggestions(self.query_one("#add-ticker-input", Input).value or "")
        content = self.query_one("#content-switcher", ContentSwitcher)
        content.current = "dashboard"
        self._set_status(f"Tickers: {self._ticker_count()}")
        self._start_filings_polling()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        content = self.query_one("#content-switcher", ContentSwitcher)
        tab_id = event.tab.id or ""
        mapping = {
            "tab-dashboard": "dashboard",
            "tab-filings": "filings-table",
            "tab-metrics": "metrics-table",
            "tab-formulas": "formulas-table",
            "tab-widgets": "widgets-table",
        }
        content.current = mapping.get(tab_id, "dashboard")

    def _setup_tables(self) -> None:
        suggestions = self.query_one("#search-suggestions", DataTable)
        self._ensure_suggestions_table(suggestions)
        suggestions.cursor_type = "row"
        suggestions.zebra_stripes = True

        filings_table = self.query_one("#filings-table", DataTable)
        if not filings_table.columns:
            filings_table.add_columns("Date", "Type", "Ticker", "Title", "New")
        filings_table.cursor_type = "row"
        filings_table.zebra_stripes = True

        metrics_table = self.query_one("#metrics-table", DataTable)
        if not metrics_table.columns:
            metrics_table.add_columns("Ticker", "Filing", "Metric", "Value")
        metrics_table.cursor_type = "row"
        metrics_table.zebra_stripes = True

        formulas_table = self.query_one("#formulas-table", DataTable)
        if not formulas_table.columns:
            formulas_table.add_columns("Name", "Expression", "Sample Value")
        formulas_table.cursor_type = "row"
        formulas_table.zebra_stripes = True

        widgets_table = self.query_one("#widgets-table", DataTable)
        if not widgets_table.columns:
            widgets_table.add_columns("Name", "Type", "Description")
        widgets_table.cursor_type = "row"
        widgets_table.zebra_stripes = True

    def _ensure_suggestions_table(self, table: DataTable) -> None:
        expected_keys = ["add", "symbol", "name", "exchange", "cik"]
        current_keys = [key.value for key in table.columns.keys()] if table.columns else []
        if current_keys == expected_keys:
            return

        table.clear(columns=True)
        table.add_column("Add", width=3, key="add")
        table.add_column("Symbol", width=7, key="symbol")
        table.add_column("Name", width=18, key="name")
        table.add_column("Exch", width=6, key="exchange")
        table.add_column("CIK", width=10, key="cik")

    def _mark_suggestion_added(self, row_key) -> None:
        suggestions = self.query_one("#search-suggestions", DataTable)
        suggestions.update_cell(row_key, "add", Text("[x]", style="bold green"))
        for col_key in ("symbol", "name", "exchange", "cik"):
            value = suggestions.get_cell(row_key, col_key)
            plain = value.plain if isinstance(value, Text) else ("" if value is None else str(value))
            suggestions.update_cell(row_key, col_key, Text(plain, style="green"))

    def action_focus_add_ticker(self) -> None:
        add_input = self.query_one("#add-ticker-input", Input)
        add_input.focus()

    def _remove_selected_ticker(self) -> None:
        tree = self.query_one("#watchlist-tree", Tree)
        node = tree.cursor_node
        if node is None or not isinstance(node.data, Ticker):
            return
        symbol = node.data.symbol
        ticker = next((t for t in dao.list_watchlist(self.session) if t.symbol == symbol), None)
        if ticker:
            dao.remove_from_watchlist(self.session, ticker)
            self.refresh_watchlist()
            if self.filter_symbol == symbol:
                self.filter_symbol = None
                self.refresh_filings_table()
            # Clear selection safely
            tree.root.collapse_all()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-ticker-button":
            self._add_ticker_from_input()
        if event.button.id == "remove-ticker-button":
            self._remove_selected_ticker()
        if event.button.id == "add-note-button":
            self._add_note()
        if event.button.id == "delete-note-button":
            self._delete_selected_note()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "add-ticker-input":
            self.refresh_search_suggestions(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "search-table":
            row = event.data_table.get_row(event.row_key)
            if row:
                symbol = row[0]
                # Add to watchlist when selected in search results.
                ticker = dao.add_ticker(self.session, symbol=symbol)
                dao.add_to_watchlist(self.session, ticker)
                self.filter_symbol = symbol
                self.refresh_watchlist()
                self.refresh_filings_table()
                self.refresh_filings_from_sec([symbol])
                self.pop_screen()
        if event.data_table.id == "search-suggestions":
            try:
                symbol_cell = event.data_table.get_cell(event.row_key, "symbol")
            except Exception:
                return
            symbol = symbol_cell.plain if isinstance(symbol_cell, Text) else str(symbol_cell)
            symbol = symbol.strip()
            if not symbol:
                return

            # Add to watchlist and mark as added without closing suggestions.
            existing = next((t for t in dao.list_watchlist(self.session) if t.symbol == symbol), None)
            if not existing:
                ticker = dao.add_ticker(self.session, symbol=symbol)
                dao.add_to_watchlist(self.session, ticker)
            self.filter_symbol = symbol
            self.refresh_watchlist()
            self.refresh_filings_table()
            self.refresh_filings_from_sec([symbol])
            try:
                self._mark_suggestion_added(event.row_key)
            except Exception:
                pass

    def _add_ticker_from_input(self) -> None:
        input_widget = self.query_one("#add-ticker-input", Input)
        symbol = (input_widget.value or "").strip()
        if not symbol:
            return
        ticker = dao.add_ticker(self.session, symbol=symbol)
        dao.add_to_watchlist(self.session, ticker)
        input_widget.value = ""
        self.refresh_watchlist()
        self.refresh_filings_table()
        self.refresh_search_suggestions("")
        self.refresh_filings_from_sec([ticker.symbol])

    def refresh_watchlist(self) -> None:
        tree = self.query_one("#watchlist-tree", Tree)
        tree.clear()
        root = tree.root
        tickers = dao.list_watchlist(self.session)
        alert_counts = dao.unread_alert_counts(self.session)
        for ticker in tickers:
            alert_count = alert_counts.get(ticker.id, 0)
            label = f"{ticker.symbol}"
            if alert_count:
                label += f" ({alert_count} alerts)"
            node = root.add(label, data=ticker)
            notes = dao.list_notes_for_ticker(self.session, ticker, limit=20)
            for note in notes:
                node.add(f"Note: {note.title}", data=note)
        tree.root.expand()
        self._set_status(f"Status: Watchlist {len(tickers)} | Alerts {sum(int(c) for c in alert_counts.values())}")

    def refresh_filings_table(self) -> None:
        filings_table = self.query_one("#filings-table", DataTable)
        filings_table.clear()
        symbols = [self.filter_symbol] if self.filter_symbol else [t.symbol for t in dao.list_watchlist(self.session)]
        if not symbols:
            return

        rows = dao.list_filings_for_symbols(self.session, symbols, limit=200)
        for filing, ticker in rows:
            date_display = filing.date.isoformat() if hasattr(filing.date, "isoformat") else str(filing.date)
            filings_table.add_row(date_display, filing.type, ticker.symbol, filing.title or "", "NEW" if filing.is_new else "")

    def action_refresh_filings(self) -> None:
        self.refresh_filings_from_sec()

    def _start_filings_polling(self) -> None:
        """
        Periodically refresh filings for the current watchlist (SEC only for now).
        """
        interval = max(30, int(self.config.poll_interval_seconds))
        self.set_interval(interval, self.refresh_filings_from_sec, name="sec_filings_poll")
        self.refresh_filings_from_sec()

    def refresh_filings_from_sec(self, symbols: list[str] | None = None) -> None:
        """
        Refresh SEC filings in a background worker to keep the UI responsive.
        """
        watchlist = dao.list_watchlist(self.session)
        if not watchlist:
            return
        target = ", ".join(symbols) if symbols else f"{len(watchlist)} tickers"
        self._set_status(f"Status: Refreshing SEC filings ({target})...")
        self._refresh_filings_worker(symbols)

    @work(thread=True, exclusive=True, group="sec_filings")
    def _refresh_filings_worker(self, symbols: list[str] | None = None) -> None:
        session = get_session(self.engine)
        try:
            poller = Poller(session, self.config)
            new_count = len(poller.run_once(symbols=symbols))
        except Exception as exc:
            self.call_from_thread(self._set_status, f"Status: SEC filings refresh failed ({exc})")
            return
        finally:
            try:
                session.close()
            except Exception:
                pass

        self.call_from_thread(self._on_filings_refreshed, new_count)

    def _on_filings_refreshed(self, new_count: int) -> None:
        try:
            self.session.expire_all()
        except Exception:
            pass
        if new_count:
            self.refresh_watchlist()
        self.refresh_filings_table()
        self._set_status(f"Status: Filings refreshed (+{new_count} new)")

    def action_refresh_sec_tickers(self) -> None:
        """
        Fetch SEC ticker list (with exchange/CIK) and upsert into DB.
        """
        self._set_status("Status: Loading SEC tickers...")
        try:
            if self._load_sec_tickers():
                self.refresh_watchlist()
                self._set_status(f"Status: Loaded tickers ({self._ticker_count()})")
            else:
                self._set_status("Status: SEC ticker load skipped")
        except Exception as exc:
            # Log the error to the console; UI notification can be added later.
            print(f"[SEC ticker load failed] {exc}")
            self._set_status("Status: SEC ticker load failed")

    def action_show_alerts(self) -> None:
        self.push_screen(AlertsModal(self.session))

    def action_show_search(self) -> None:
        self.push_screen(SearchModal(self.session, total_tickers=self._ticker_count()))

    def _seed_mock_data_if_empty(self) -> None:
        """
        Populate mock tickers/filings on first run to make the UI non-empty.
        """
        # Keep watchlist empty by default; only add tickers explicitly.
        pass

    def _load_sec_tickers_if_needed(self) -> None:
        """
        Load SEC ticker list into the DB when CIK/exchange data is missing.
        """
        existing = dao.list_tickers(self.session)
        have_cik = any(t.cik for t in existing)
        # If we already have a reasonable list with CIKs, skip.
        if have_cik and len(existing) > 50:
            return
        self._load_sec_tickers()

    def refresh_metrics_table(self) -> None:
        metrics_table = self.query_one("#metrics-table", DataTable)
        metrics_table.clear()
        # Real metrics extraction not wired yet.

    def refresh_formulas_table(self) -> None:
        table = self.query_one("#formulas-table", DataTable)
        table.clear()
        # Formulas not implemented yet.

    def refresh_widgets_table(self) -> None:
        table = self.query_one("#widgets-table", DataTable)
        table.clear()
        # Widgets not implemented yet.

    def _set_status(self, message: str) -> None:
        try:
            status = self.query_one("#status-bar", Static)
            status.update(message)
        except Exception:
            pass

    def _ticker_count(self) -> int:
        return len(dao.list_tickers(self.session))

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        data = node.data
        if isinstance(data, Ticker):
            self.filter_symbol = data.symbol
            self.refresh_filings_table()
        else:
            # If selecting a note or other node, do not change selection.
            return

    def refresh_search_suggestions(self, query: str) -> None:
        suggestions = self.query_one("#search-suggestions", DataTable)
        self._ensure_suggestions_table(suggestions)
        suggestions.clear()
        q = query.strip()
        if not q:
            self.query_one("#suggestions-panel", Vertical).add_class("hidden")
            return
        results = dao.search_tickers(self.session, q, limit=15)
        panel = self.query_one("#suggestions-panel", Vertical)
        if results:
            panel.remove_class("hidden")
        else:
            panel.add_class("hidden")
        watchlist_symbols = {t.symbol for t in dao.list_watchlist(self.session)}
        for ticker in results:
            in_watchlist = ticker.symbol in watchlist_symbols
            add_cell = Text("[x]", style="bold green") if in_watchlist else Text("[+]", style="bold")
            style = "green" if in_watchlist else ""
            symbol_cell = Text(ticker.symbol, style=style) if in_watchlist else ticker.symbol
            name_cell = Text(ticker.name or "", style=style) if in_watchlist else (ticker.name or "")
            exch_cell = Text(ticker.exchange or "", style=style) if in_watchlist else (ticker.exchange or "")
            cik_cell = Text(ticker.cik or "", style=style) if in_watchlist else (ticker.cik or "")
            suggestions.add_row(add_cell, symbol_cell, name_cell, exch_cell, cik_cell)

    def _add_note(self) -> None:
        if not self.filter_symbol:
            return
        ticker = next((t for t in dao.list_watchlist(self.session) if t.symbol == self.filter_symbol), None)
        if not ticker:
            return
        title = (self.query_one("#note-title", Input).value or "").strip()
        if not title:
            return
        attachment = (self.query_one("#note-attachment", Input).value or "").strip()
        dao.add_note(self.session, ticker, title=title, content=None, attachment=attachment or None)
        self.query_one("#note-title", Input).value = ""
        self.query_one("#note-attachment", Input).value = ""
        self.refresh_watchlist()

    def _load_sec_tickers(self) -> bool:
        """
        Try local SEC JSON files first; fall back to network fetch.
        Returns True on success, False otherwise.
        """
        local_files = [
            Path("company_tickers.json"),
            Path("sec_tickers.json"),
        ]
        exchange_files = [
            Path("company_tickers_exchange.json"),
            Path("sec_tickers_exchange.json"),
        ]
        for primary in local_files:
            if primary.exists():
                exchange = next((p for p in exchange_files if p.exists()), None)
                try:
                    tickers = load_sec_tickers_from_file(primary, exchange)
                    rows = [
                        {"symbol": t.ticker, "name": t.title, "cik": t.cik_padded, "exchange": t.exchange}
                        for t in tickers
                    ]
                    dao.upsert_tickers_bulk(self.session, rows)
                    return True
                except Exception as exc:
                    print(f"[Local SEC ticker load failed {primary}] {exc}")
        try:
            tickers = fetch_sec_tickers(with_exchange=True)
            rows = [
                {"symbol": t.ticker, "name": t.title, "cik": t.cik_padded, "exchange": t.exchange}
                for t in tickers
            ]
            dao.upsert_tickers_bulk(self.session, rows)
            return True
        except Exception as exc:
            print(f"[Network SEC ticker load failed] {exc}")
            return False

def _mock_cik(symbol: str) -> str:
    sample = {"AAPL": "0000320193", "MSFT": "0000789019", "GOOGL": "0001652044"}
    return sample.get(symbol.upper(), "")


def _mock_exchange(symbol: str) -> str:
    return "NASDAQ"


class AlertsModal(ModalScreen[None]):
    """
    Modal to display unread alerts.
    """

    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("q", "dismiss", "Close")]

    def __init__(self, session) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        yield Static("Unread alerts", id="alerts-title")
        table = DataTable(id="alerts-table")
        table.add_columns("Date", "Ticker", "Type", "Title")
        yield table

    def on_mount(self) -> None:
        self.refresh_alerts()

    def refresh_alerts(self) -> None:
        table = self.query_one("#alerts-table", DataTable)
        table.clear()
        alerts = dao.unread_alerts(self.session)
        for alert in alerts:
            filing = alert.filing
            ticker = filing.ticker
            date_display = filing.date.isoformat() if hasattr(filing.date, "isoformat") else str(filing.date)
            table.add_row(date_display, ticker.symbol, filing.type, filing.title or "")
        # Mark as read after showing
        dao.mark_alerts_read(self.session, alerts)


class SearchModal(ModalScreen[None]):
    """
    Modal to search tickers by symbol, CIK, or name.
    """

    BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("enter", "run_search", "Search")]

    def __init__(self, session, total_tickers: int = 0) -> None:
        super().__init__()
        self.session = session
        self.total_tickers = total_tickers

    def compose(self) -> ComposeResult:
        yield Static("Search tickers (symbol/CIK/name)", id="search-title")
        yield Input(placeholder="e.g., AAPL or 0000320193 or Apple", id="search-input")
        yield Button("Search", id="search-button")
        yield Static(f"Total tickers in DB: {self.total_tickers}", id="search-count")
        table = DataTable(id="search-table")
        table.add_columns("Symbol", "Name", "Exchange", "CIK")
        yield table

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_run_search(self) -> None:
        self._run_search()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search-button":
            self._run_search()

    def _run_search(self) -> None:
        input_widget = self.query_one("#search-input", Input)
        query = (input_widget.value or "").strip()
        if not query:
            return
        results = dao.search_tickers(self.session, query, limit=30)
        table = self.query_one("#search-table", DataTable)
        table.clear()
        for ticker in results:
            table.add_row(ticker.symbol, ticker.name or "", ticker.exchange or "", ticker.cik or "")
        self.query_one("#search-count", Static).update(f"Total tickers in DB: {self.total_tickers} | Results: {len(results)}")


def run() -> None:
    app = FinancialTerminal()
    app.run()


if __name__ == "__main__":
    run()
