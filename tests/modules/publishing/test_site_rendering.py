"""The rendered HTML — what actually reaches a browser.

Assertions are on content and structure, not on exact markup: the CSS will
change, the guarantees will not. The two that matter most are that the site is
offline-complete (no external request can fail or leak) and that interpolated
text is escaped (a document is untrusted input to the renderer even though it
came from the store).
"""

from __future__ import annotations

import re

from docir.modules.publishing.api import PublishRequest, build_site, build_site_builder
from docir.modules.publishing.infra.rendering import render_site

_DOCS = [
    {
        "id": "adr-0001",
        "title": "Old way",
        "description": "Previous.",
        "type": "decision",
        "status": "superseded",
        "created": "2026-01-01",
        "updated": "2026-01-02",
        "body": "## Context\n\nThe old approach with `code` and a [link](https://x.test).\n",
    },
    {
        "id": "adr-0002",
        "title": "New way",
        "description": "Replacement.",
        "type": "decision",
        "status": "accepted",
        "created": "2026-02-01",
        "updated": "2026-02-01",
        "body": "Body.",
        "related": [{"target": "adr-0001", "kind": "supersedes"}],
        "stale": True,
    },
]


def _pages() -> dict[str, str]:
    return render_site(build_site(_DOCS), title="Docs", version="1.2.3")


class TestStructure:
    def test_one_page_per_document_plus_index_and_graph(self) -> None:
        pages = _pages()
        assert set(pages) == {
            "index.html",
            "graph.html",
            "adr-0001.html",
            "adr-0002.html",
            "adr-0001.md",
            "adr-0002.md",
        }

    def test_the_markdown_source_is_published_beside_each_page(self) -> None:
        """ "View as Markdown" has to open something. The body, verbatim —
        a reader who wants to quote or diff the document should not have to
        install docir to get at it."""
        pages = _pages()
        assert pages["adr-0001.md"] == _DOCS[0]["body"]
        assert 'href="adr-0001.md"' in pages["adr-0001.html"]

    def test_the_index_links_every_document(self) -> None:
        index = _pages()["index.html"]
        assert 'href="adr-0001.html"' in index
        assert 'href="adr-0002.html"' in index

    def test_the_body_is_rendered_as_markdown(self) -> None:
        page = _pages()["adr-0001.html"]
        assert 'id="context">Context' in page
        assert "<code>code</code>" in page
        assert "&#35;&#35; Context" not in page

    def test_both_edge_directions_are_shown(self) -> None:
        """No other ADR site renders the inbound half.

        One panel carries both directions; the arrow and the phrasing say
        which is which, because "supersedes" over an inbound edge states the
        opposite of the truth.
        """
        old = _pages()["adr-0001.html"]
        assert "\u2190 superseded by" in old, "the inbound edge is not phrased from this page"
        assert 'href="adr-0002.html"' in old
        new = _pages()["adr-0002.html"]
        assert "supersedes \u2192" in new
        assert 'href="adr-0001.html"' in new

    def test_a_superseded_document_says_so_before_its_body(self) -> None:
        """The one thing a reader of an old decision must not miss."""
        old = _pages()["adr-0001.html"]
        banner = old.index("Not the last word")
        assert banner < old.index('<div class="body">')
        assert "New way" in old[banner : banner + 400]

    def test_staleness_is_visible_on_the_index(self) -> None:
        index = _pages()["index.html"]
        assert "past their review cadence" in index
        assert 'class="chip stale"' in index


class TestGraphPage:
    """The corpus as a map — the data reaches the page and stays inert."""

    def test_the_graph_embeds_every_document(self) -> None:
        graph = _pages()["graph.html"]
        assert '"id":"adr-0001"' in graph
        assert '"id":"adr-0002"' in graph
        assert '"k":"supersedes"' in graph

    def test_the_card_links_to_the_document_page(self) -> None:
        """The graph is exploration; the page is the destination. A card
        without the link strands the reader on a site that has full pages."""
        assert 'class="open" href="${n.id}.html"' in _pages()["graph.html"]

    def test_a_title_cannot_terminate_the_script(self) -> None:
        """The HTML parser ends a script at the first `</script` it sees,
        inside a JSON string literal or not — a hostile title would
        otherwise parse as markup."""
        pages = render_site(
            build_site([dict(_DOCS[0], title="</script><img src=x onerror=alert(1)>")]),
            title="Docs",
            version="1",
        )
        graph = pages["graph.html"]
        assert "<\\/script><img" in graph
        assert "</script><img" not in graph

    def test_the_graph_uses_the_site_theme_tokens(self) -> None:
        """One site, one chrome: the map must not ship a second palette for
        the page furniture."""
        graph = _pages()["graph.html"]
        assert "--accent:#0969da" in graph, "the site's light accent is absent"
        assert "--accent:#58a6ff" in graph, "the site's dark accent is absent"

    def test_an_empty_corpus_still_renders_a_page(self) -> None:
        """`build` on an empty store writes a site; the graph page must not
        be the one file that throws on zero nodes."""
        graph = render_site(build_site([]), title="Docs", version="1")["graph.html"]
        assert '"nodes":[]' in graph

    def test_an_empty_corpus_draws_no_ghost_ring(self) -> None:
        """With no types the hub is undefined, and [hub, ...] laid out one
        ring labelled "undefined 0" on an otherwise blank canvas."""
        graph = render_site(build_site([]), title="Docs", version="1")["graph.html"]
        assert "const order=types.length?" in graph

    def test_index_and_documents_link_to_the_graph(self) -> None:
        """A document page deep-links to itself: the reader lands on the map
        with the document they were just reading already pinned."""
        pages = _pages()
        assert 'href="graph.html"' in pages["index.html"]
        assert 'href="graph.html#adr-0001"' in pages["adr-0001.html"]

    def test_the_graph_honours_the_fragment_deep_link(self) -> None:
        """graph.html#<id> must pin that document on load — the other half of
        the document page's link."""
        graph = _pages()["graph.html"]
        assert "location.hash.slice(1)" in graph
        assert "if(target&&byId[target]) show(target);" in graph

    def test_the_graph_links_back_to_the_index(self) -> None:
        assert 'href="index.html"' in _pages()["graph.html"]

    def test_the_graph_wears_the_site_top_bar(self) -> None:
        """It had its own header — padding-derived height, wrapping onto two
        rows — so the one page every other page advertises was the one that
        looked like a different tool. Same component, same measurements."""
        pages = _pages()
        for name in ("index.html", "graph.html"):
            bar = pages[name][pages[name].index(".topbar{") :]
            rule = bar[: bar.index("}")]
            assert "height:56px" in rule and "padding:0 1.25rem" in rule, name
            assert "gap:.9rem" in rule, name
        assert '<header class="topbar">' in pages["graph.html"]
        assert '<a class="brand" href="index.html">' in pages["graph.html"]

    def test_the_brand_measures_the_same_on_every_page(self) -> None:
        """The muted tail rendered at 14.4px on a page and 16px on the graph.

        A bare `.sub{font-size:.9rem}` utility — left behind when the landing's
        stats line was renamed — captured `.brand .sub`, which the graph's
        stylesheet has no equivalent of. The tail is the wordmark's size,
        lighter and muted; only the graph was showing it correctly.
        """
        for name, page in _pages().items():
            if not page.lstrip().startswith("<!doctype"):
                continue
            assert ".brand .sub{color:var(--muted);font-weight:400}" in page, name
            assert "\n.sub{" not in page, f"{name} has an unscoped .sub rule again"

    def test_the_graph_carries_the_theme_toggle(self) -> None:
        """The theme was changeable on every page except this one, while the
        choice made elsewhere still applied here — a persisted setting with no
        control in sight to undo it."""
        graph = _pages()["graph.html"]
        assert 'id="themeBtn"' in graph
        assert "localStorage.setItem('docir-theme',v)" in graph

    def test_the_graph_edge_tone_follows_a_chosen_theme(self) -> None:
        """`--edge` keyed off `prefers-color-scheme` alone, so a reader who
        picked dark on a light OS got a dark canvas drawn with light edges."""
        assert ':root[data-theme="dark"]{--edge:' in _pages()["graph.html"]

    def test_the_card_groups_relations_like_the_document_rail(self) -> None:
        """Two buckets labelled "links to"/"linked from" made the reader work
        out which of six kinds each row was. The direction rides on the kind,
        and the phrasing is the domain's so the two panels cannot disagree."""
        graph = _pages()["graph.html"]
        assert '"supersedes":"superseded by"' in graph, "the shared vocabulary is not embedded"
        assert "INBOUND[e.k]" in graph
        # The emitted markup, not the prose around it: the comment explaining
        # what was replaced names the old headings too.
        assert ">links to ${" not in graph, "the undifferentiated buckets are back"
        assert ">relations `" in graph, "the card lost its relation count"


class TestLanding:
    """The index is the landing page: what a first visit needs, above the fold."""

    def test_corpus_stats_sit_in_the_header(self) -> None:
        index = _pages()["index.html"]
        assert "2 documents · 1 type" in index

    def test_the_stats_are_stated_once(self) -> None:
        """Sub-line *and* tiles meant a large corpus announced its own size
        twice, in two typefaces, directly above itself."""
        many = [dict(_DOCS[0], id=f"adr-1{n:03d}", title=f"Doc {n}") for n in range(11)]
        index = render_site(build_site(many), title="Docs", version="1")["index.html"]
        assert 'class="tiles"' in index
        assert "11 documents · 1 type" not in index

    def test_the_graph_is_reachable_from_every_page(self) -> None:
        """The landing-only call-to-action was the one exit a reader who
        arrived on a document could not see; the top bar is on every page."""
        pages = _pages()
        for name in ("index.html", "adr-0001.html"):
            assert '<a class="toplnk" href="graph.html">Graph</a>' in pages[name]

    def test_a_small_corpus_gets_no_recent_strip(self) -> None:
        """Five recent rows above a seven-row listing is the listing twice."""
        assert 'id="recent"' not in _pages()["index.html"]

    def test_rows_carry_structured_filter_data(self) -> None:
        """The filter works off the markup alone — type, status and date must
        be machine-readable on every filterable row, not just visible text."""
        index = _pages()["index.html"]
        assert 'data-type="decision"' in index
        assert 'data-status="accepted"' in index
        assert 'data-updated="2026-02-01"' in index

    def test_facet_options_come_from_the_corpus_with_counts(self) -> None:
        """An option no document matches filters to an empty page and looks
        broken — facets list what exists, each with its result count."""
        index = _pages()["index.html"]
        assert 'data-fv="decision"' in index
        assert 'data-fv="accepted"' in index
        assert 'data-fv="superseded"' in index
        assert 'data-fv="architecture"' not in index
        assert '<span class="n">2</span>' in index, "the type count is missing"

    def test_facets_are_multi_select_checkboxes(self) -> None:
        index = _pages()["index.html"]
        assert '<input type="checkbox" value="decision">' in index
        assert "setHit(state.type,r.dataset.type)" in index, "type match must be set-based (OR)"

    def test_a_zero_count_option_dims_instead_of_vanishing(self) -> None:
        """An option that disappears reads as a bug ("where did it go?"), and
        a selection that stops matching keeps its chip as the visible cause of
        an empty list — so options ghost at count zero and are never silently
        dropped."""
        index = _pages()["index.html"]
        assert "classList.toggle('ghost',ghost)" in index
        assert ".disabled=ghost" in index

    def test_applied_filters_render_as_removable_chips(self) -> None:
        """Chips above the list are the canonical display of applied state —
        a count-only summary forces reopening every facet to see what is on."""
        index = _pages()["index.html"]
        assert 'id="chipsBar"' in index
        assert "removeChipAt" in index
        assert 'data-chip="${i}"' in index

    def test_typed_tokens_become_chips(self) -> None:
        """The box accepts the tracker grammar (type:x, is:stale, -status:y);
        only a value the corpus actually has converts — the rest stays free
        text and searches as words."""
        index = _pages()["index.html"]
        assert "extractTokens" in index
        assert "(type|status|owner|is|updated)" in index

    def test_the_owner_facet_appears_only_when_documents_have_owners(self) -> None:
        """The site receives no schema; an owner facet over a corpus with no
        owners is an empty dropdown that looks broken."""
        assert 'id="oopts"' not in _pages()["index.html"]
        owned = render_site(
            build_site([dict(_DOCS[0], owner="maintainer")]), title="Docs", version="1"
        )["index.html"]
        assert 'id="oopts"' in owned
        assert 'data-owner="maintainer"' in owned

    def test_the_stale_toggle_appears_only_when_something_is_stale(self) -> None:
        index = _pages()["index.html"]
        assert 'id="staleTgl"' in index
        assert 'data-stale="1"' in index
        fresh = render_site(build_site([dict(_DOCS[0])]), title="Docs", version="1")["index.html"]
        assert 'id="staleTgl"' not in fresh

    def test_the_stale_banner_links_to_the_filtered_state(self) -> None:
        """The banner names a problem; the link is the queue that answers it."""
        assert 'href="?is=stale"' in _pages()["index.html"]

    def test_a_zero_result_list_offers_recovery(self) -> None:
        """A dead-end "no results" is the documented failure mode; the way out
        — remove the last step, or start over — is offered in place."""
        index = _pages()["index.html"]
        assert 'id="noHits"' in index
        assert 'id="undoLast"' in index
        assert 'id="clearAllBtn"' in index

    def test_back_undoes_filter_steps(self) -> None:
        """Users perceive each facet change as a view, so each one is a
        pushState entry Back can undo — while typing only replaces."""
        index = _pages()["index.html"]
        assert "history.pushState" in index
        assert "popstate" in index

    def test_preset_views_render_only_at_browsing_scale(self) -> None:
        """Shortcuts through a listing that fits on one screen are furniture;
        past that, one click reaches the states readers actually revisit."""
        assert 'id="views"' not in _pages()["index.html"]
        many = [
            dict(_DOCS[0], id=f"adr-1{n:03d}", title=f"Doc {n}", stale=n == 0) for n in range(11)
        ]
        index = render_site(build_site(many), title="Docs", version="1")["index.html"]
        assert 'id="views"' in index
        assert 'data-sig="is=stale"' in index
        assert "open issues" not in index, "no issue type in this corpus"

    def test_the_date_facet_offers_presets_and_a_custom_range(self) -> None:
        index = _pages()["index.html"]
        assert 'name="dpre" value="30d"' in index
        assert "last 30 days" in index
        assert 'id="dfrom"' in index and 'id="dto"' in index

    def test_hidden_means_hidden_despite_author_display_rules(self) -> None:
        """[hidden] maps to display:none only in the UA stylesheet, and the
        grid rows and flex facet labels override it — a filtered-out row
        stayed visible whenever its section did not hide with it."""
        assert "[hidden]{display:none!important}" in _pages()["index.html"]

    def test_the_filter_state_is_mirrored_into_the_url(self) -> None:
        """A filtered view must be a copyable link: the script writes the
        combined state to the query string and restores it on load."""
        index = _pages()["index.html"]
        assert "URLSearchParams" in index
        assert "history.replaceState" in index
        assert "p.get('updated')" in index
        assert "p.get('from')" in index

    def test_a_garbage_date_in_the_url_is_dropped(self) -> None:
        """The from/to variables feed string comparisons directly, and
        "?from=garbage" sorts above every ISO date — the page silently
        filtered to nothing."""
        assert "isoRe.test" in _pages()["index.html"]

    def test_a_larger_corpus_gets_one_and_it_is_not_filterable(self) -> None:
        """The strip mirrors rows the type sections already carry; if its rows
        joined the filter, every match would be counted (and shown) twice."""
        many = [
            dict(_DOCS[0], id=f"adr-1{n:03d}", title=f"Doc {n}", updated=f"2026-01-{n + 1:02d}")
            for n in range(11)
        ]
        index = render_site(build_site(many), title="Docs", version="1")["index.html"]
        assert 'id="recent"' in index
        recent = index[index.index('id="recent"') : index.index("</section>")]
        assert "data-hay" not in recent, "recent rows must not join the filter"
        assert "Doc 10" in recent, "not sorted by updated date"


class TestShell:
    """The persistent chrome: top bar, corpus sidebar, palette, theme, rail."""

    def test_every_page_carries_the_corpus_sidebar(self) -> None:
        """A document page used to have two exits; now it has the corpus.
        The current document is marked, so the reader knows where they are."""
        pages = _pages()
        for name in ("index.html", "adr-0001.html", "adr-0002.html"):
            assert 'class="sidebar"' in pages[name]
            assert "Old way" in pages[name] and "New way" in pages[name]
        assert 'class="on" data-doc' in pages["adr-0001.html"]

    def test_the_index_carries_a_corpus_rail(self) -> None:
        """The landing's rail: how healthy the corpus is, and what is in it.
        A reader who never runs the CLI still sees what `check` reports."""
        index = _pages()["index.html"]
        assert "Corpus health" in index
        assert "Dangling edges" in index
        assert "Types" in index

    def test_type_names_read_as_headings_not_keys(self) -> None:
        """`release_note` is a schema key; a heading listing eighteen of them
        is prose. The facet option keeps the raw value — it has to match the
        `type:release_note` token the same box accepts.
        """
        index = render_site(
            build_site([dict(_DOCS[0], id="rel-1", type="release_note")]),
            title="Docs",
            version="1",
        )["index.html"]
        assert "Release notes" in index
        assert 'data-fv="release_note"' in index, "the facet value must stay the schema key"

    def test_sections_and_nav_carry_the_type_colour(self) -> None:
        """The dot is reinforcement; the name beside it is the encoding.

        The token must be matched with its fallback, the form `_type_dot`
        actually emits. Counting the bare `var(--t-decision)` matched nothing
        of the sort: the only two occurrences on the page were inside the old
        brandmark's conic-gradient, so this passed for two years' worth of
        commits while asserting nothing about the sidebar or the headings —
        and went red the moment the mark became real art.
        """
        index = _pages()["index.html"]
        dot = "var(--t-decision,var(--muted))"
        assert index.count(dot) >= 3, "sidebar group, section heading and rail legend"

    def test_the_document_actions_row_is_separate_from_the_chips(self) -> None:
        """A chip states a fact; a button does something. Mixing them made
        "view in graph" read as metadata."""
        page = _pages()["adr-0001.html"]
        assert 'class="actions"' in page
        assert "View in graph" in page
        assert 'class="abtn"' in page

    def test_the_palette_exists_and_indexes_the_sidebar(self) -> None:
        """⌘K search works offline because its data IS the sidebar links —
        one copy of the corpus per page, so the two cannot disagree."""
        page = _pages()["adr-0001.html"]
        assert 'id="palScrim"' in page
        assert ".sidebar a[data-doc]" in page

    def test_the_theme_choice_paints_before_the_stylesheet(self) -> None:
        """A chosen theme must not flash the wrong one on load: the restore
        script runs before <style>, and the toggle persists the choice."""
        page = _pages()["index.html"]
        assert page.index("docir-theme") < page.index("<style>")
        assert 'id="themeBtn"' in page

    def test_the_breadcrumb_leaf_is_the_docir_id(self) -> None:
        """One index per document: chrome identifies a document only by its
        docir id; sequence labels inside titles are title text, not identity."""
        page = _pages()["adr-0001.html"]
        assert '<span class="bc-id">adr-0001</span>' in page
        assert 'class="chip docid"' in page
        assert "docir get adr-0001" in page, "the copyable command names the same id"

    def test_relations_group_by_kind(self) -> None:
        """The kind is a heading over its targets, not a per-row suffix."""
        new = _pages()["adr-0002.html"]
        assert '<span class="kind">supersedes →</span>' in new

    def test_the_rail_carries_trust_and_the_local_map(self) -> None:
        page = _pages()["adr-0001.html"]
        assert "Trust" in page
        assert "Local map" in page
        # The map's neighbour is a real link to the other page, inside the svg.
        map_part = page[page.index("Local map") :]
        assert 'href="adr-0002.html"' in map_part[: map_part.index("</svg>")]

    def test_a_document_with_no_relations_still_links_to_the_graph(self) -> None:
        """The local map renders only with neighbours; the graph deep-link
        must not disappear with it."""
        pages = render_site(build_site([dict(_DOCS[0])]), title="Docs", version="1")
        page = pages["adr-0001.html"]
        assert "Local map" not in page
        assert 'href="graph.html#adr-0001"' in page

    def test_prev_next_stay_within_the_type(self) -> None:
        """adr-0001 is the older decision: its only neighbour is the newer
        one, labelled previous (the listing is newest-first)."""
        page = _pages()["adr-0001.html"]
        assert "previous" in page
        assert 'class="pn"' in page

    def test_relation_links_carry_hover_preview_data(self) -> None:
        """The Quartz pattern: the target's summary answers "what is this?"
        without the click, from data the renderer already resolved."""
        old = _pages()["adr-0001.html"]
        assert 'data-pt="New way"' in old
        assert 'data-pd="Replacement."' in old

    def test_code_blocks_are_framed_titled_and_copyable(self) -> None:
        """The header carries the language and the copy button. The button
        sits outside the <pre> it copies, so it cannot copy itself — the
        failure the old floating button had to work around."""
        page = render_site(
            build_site([dict(_DOCS[0], body="```bash\ndocir get x --json\n```\n")]),
            title="Docs",
            version="1",
        )["adr-0001.html"]
        assert '<div class="codeblk"><div class="hd"><span>bash</span>' in page
        assert '<button type="button">Copy</button>' in page
        assert ".codeblk .hd button" in page, "the handler must find the header button"

    def test_code_blocks_are_syntax_coloured(self) -> None:
        """A snippet is the part a reader copies; one flat grey makes them
        parse `docir build --out` before they can read it."""
        page = render_site(
            build_site([dict(_DOCS[0], body="```bash\n# note\ndocir build --out site/\n```\n")]),
            title="Docs",
            version="1",
        )["adr-0001.html"]
        assert '<span class="sy-cmt"># note</span>' in page
        assert '<span class="sy-fn">docir</span>' in page
        assert '<span class="sy-kw">build</span>' in page
        assert '<span class="sy-flag">--out</span>' in page

    def test_an_unknown_language_is_not_guessed_at(self) -> None:
        """A wrong colour asserts a structure that is not there. The frame
        still renders; only the colouring is withheld."""
        page = render_site(
            build_site([dict(_DOCS[0], body="```brainfuck\n# not a comment\n```\n")]),
            title="Docs",
            version="1",
        )["adr-0001.html"]
        assert "<span>brainfuck</span>" in page
        assert "sy-cmt" not in page[page.index('<div class="body">') :]

    def test_the_foot_hints_name_the_cli_edit_path(self) -> None:
        """The site is read-only; the way to change a page is the CLI, and
        the page says so with the exact command."""
        page = _pages()["adr-0001.html"]
        assert "docir update adr-0001" in page

    def test_stat_tiles_render_only_at_browsing_scale(self) -> None:
        assert 'class="tiles"' not in _pages()["index.html"]
        many = [
            dict(_DOCS[0], id=f"adr-1{n:03d}", title=f"Doc {n}", stale=n == 0) for n in range(11)
        ]
        index = render_site(build_site(many), title="Docs", version="1")["index.html"]
        assert 'class="tiles"' in index
        assert 'href="?is=stale"' in index

    def test_the_stale_queue_link_appears_only_when_something_is_stale(self) -> None:
        assert 'href="index.html?is=stale"' in _pages()["adr-0001.html"]
        fresh = render_site(build_site([dict(_DOCS[0])]), title="Docs", version="1")
        assert "?is=stale" not in fresh["adr-0001.html"]


class TestSelfContained:
    def test_the_renderer_adds_no_external_subresource(self) -> None:
        """A published site must work from file:// and behind a locked-down host.

        Also a privacy property: a page that fetches a font tells someone else
        who is reading your architecture decisions.

        Subresources only — a stylesheet, a script, an image. An `<a href>` to
        the web is the *document author's* link and must survive: this checks
        what the renderer brings, not what a body says.
        """
        for name, page in _pages().items():
            assert not re.search(r'<link[^>]+href="(?!data:)', page), f"{name} pulls a stylesheet"
            assert not re.search(r"<script[^>]+src=", page), f"{name} pulls a script"
            assert not re.search(r"<img[^>]+src=\"https?://", page), f"{name} pulls an image"

    def test_an_authored_link_survives(self) -> None:
        """The other half of the same rule: content links are not the renderer's."""
        assert 'href="https://x.test"' in _pages()["adr-0001.html"]

    def test_styles_are_inlined(self) -> None:
        assert "<style>" in _pages()["index.html"]


class TestEscaping:
    def test_titles_are_escaped_not_rendered(self) -> None:
        """A title is text. A document titled `<script>` is a title, not a script."""
        pages = render_site(
            build_site(
                [
                    dict(
                        _DOCS[0],
                        title="<script>alert(1)</script>",
                        description="a & b",
                    )
                ]
            ),
            title="Docs",
            version="1",
        )
        page = pages["adr-0001.html"]
        assert "<script>alert(1)</script>" not in page.replace("<script>const rows", ""), (
            "the title was emitted as markup"
        )
        assert "&lt;script&gt;" in page
        assert "a &amp; b" in page


class TestWriting:
    def test_it_writes_the_files_and_reports_them(self, tmp_path) -> None:
        result = build_site_builder().build(
            PublishRequest(out=tmp_path / "site", documents=_DOCS, title="Docs", version="1")
        )
        assert result.documents == 2
        assert result.stale == 1
        assert (tmp_path / "site" / "index.html").exists()
        assert (tmp_path / "site" / "search-index.json").exists()

    def test_a_rebuild_removes_pages_for_deleted_documents(self, tmp_path) -> None:
        """The site is derived: a deleted document must not survive as a page.

        Without the sweep, a corpus that shrinks publishes a page nobody can
        reach from the index and nobody knows is stale — the web equivalent of
        an index row whose file is gone.
        """
        out = tmp_path / "site"
        builder = build_site_builder()
        builder.build(PublishRequest(out=out, documents=_DOCS, version="1"))
        assert (out / "adr-0002.html").exists()

        builder.build(PublishRequest(out=out, documents=_DOCS[:1], version="1"))
        assert not (out / "adr-0002.html").exists()
        assert (out / "adr-0001.html").exists()

    def test_it_refuses_a_directory_it_did_not_build(self, tmp_path) -> None:
        """`--out` is a path a person types, and it regenerates what it finds."""
        import pytest

        from docir.platform.errors import DocirError

        out = tmp_path / "src"
        out.mkdir()
        (out / "important.py").write_text("# not a site", encoding="utf-8")

        with pytest.raises(DocirError, match="not empty"):
            build_site_builder().build(PublishRequest(out=out, documents=_DOCS, version="1"))
        assert (out / "important.py").exists()

    def test_force_overwrites_it(self, tmp_path) -> None:
        out = tmp_path / "src"
        out.mkdir()
        (out / "important.py").write_text("# not a site", encoding="utf-8")
        result = build_site_builder().build(
            PublishRequest(out=out, documents=_DOCS, version="1", force=True)
        )
        assert result.documents == 2

    def test_an_empty_directory_is_fine(self, tmp_path) -> None:
        out = tmp_path / "site"
        out.mkdir()
        assert (
            build_site_builder()
            .build(PublishRequest(out=out, documents=_DOCS, version="1"))
            .documents
            == 2
        )


class TestReadability:
    """Fixes that came from opening the site in a browser, not from the markup.

    Each of these was a real defect found at a real viewport; without a test
    they are one refactor away from coming back, and none of them would fail
    anything else in the suite.
    """

    def test_a_body_repeating_the_title_does_not_print_it_twice(self) -> None:
        """docir's own convention restates the title as the body's first line.

        Published, that was the title twice — and the second one *larger*,
        because a body `h1` outranks the page heading.
        """
        pages = render_site(
            build_site([dict(_DOCS[0], body="# Old way\n\nThe body proper.\n")]),
            title="Docs",
            version="1",
        )
        # Exactly one h1 per page: the header's. The body's repeat is gone.
        # (Counting the text would also match <title>, which is correct there.)
        assert pages["adr-0001.html"].count("<h1") == 1

    def test_a_body_heading_that_is_not_the_title_survives(self) -> None:
        """Only the *repeat* is dropped; a real first heading is content."""
        pages = render_site(
            build_site([dict(_DOCS[0], body="# Something else\n\nBody.\n")]),
            title="Docs",
            version="1",
        )
        page = pages["adr-0001.html"]
        assert ">Something else" in page
        assert page.count("<h1") == 2, "the header's and the body's own"

    def test_headings_are_addressable(self) -> None:
        """The site's answer to `get --section`: a link to one section."""
        body = "\n".join(f"## Section {n}\n\nText for {n}.\n" for n in range(1, 5))
        pages = render_site(build_site([dict(_DOCS[0], body=body)]), title="Docs", version="1")
        page = pages["adr-0001.html"]
        assert 'id="section-1"' in page
        assert 'href="#section-1"' in page, "no anchor to link the section with"

    def test_repeated_headings_get_distinct_ids(self) -> None:
        """Two sections called Context is normal; two links to one is not."""
        body = "## Context\n\nA.\n\n## Decision\n\nB.\n\n## Context\n\nC.\n"
        pages = render_site(build_site([dict(_DOCS[0], body=body)]), title="Docs", version="1")
        page = pages["adr-0001.html"]
        assert 'id="context"' in page and 'id="context-1"' in page

    def test_a_long_document_gets_a_table_of_contents(self) -> None:
        """Section navigation — the site's answer to `get --section`."""
        body = "\n".join(f"## Section {n}\n\nText.\n" for n in range(1, 6))
        page = render_site(build_site([dict(_DOCS[0], body=body)]), title="Docs", version="1")[
            "adr-0001.html"
        ]
        assert "On this page" in page
        assert page.index("On this page") < page.index('<div class="body">')
        assert ".rail .toc a" in page, "the scroll-spy must find the contents links"

    def test_a_short_document_gets_none(self) -> None:
        """Two links above a short body are furniture, not navigation."""
        page = render_site(
            build_site([dict(_DOCS[0], body="## One\n\nText.\n")]), title="Docs", version="1"
        )["adr-0001.html"]
        assert "On this page" not in page

    def test_relations_sit_above_the_body(self) -> None:
        """They were 4,068px down a 4,596px page — present and invisible.

        The rail renders before the content column in source order, so the
        guarantee survives the move out of the body's own column.
        """
        page = _pages()["adr-0002.html"]
        assert page.index("Relations") < page.index('<div class="body">')

    def test_type_status_and_tags_are_visually_distinct(self) -> None:
        """One page read `architecture · active · architecture · persistence`.

        Three different kinds of fact rendered as three identical grey pills,
        with the same word meaning a type in one and a tag in the next.
        """
        page = render_site(
            build_site([dict(_DOCS[0], tags=["decision", "auth"])]),
            title="Docs",
            version="1",
        )["adr-0001.html"]
        assert 'class="chip type"' in page
        # Status carries its semantic colour: superseded reads as a warning,
        # not the same grey pill as everything else.
        assert 'class="chip status st-warn"' in page
        assert 'class="chip tag"' in page
        # The type is `decision` and so is one of the tags; they must not read
        # the same, which is exactly the case that exposed this.
        assert ">#decision<" in page, "a tag is not marked as one"

    def test_the_index_does_not_repeat_its_own_count(self) -> None:
        """It read "105 documents · 105 of 105" until you typed something."""
        index = _pages()["index.html"]
        assert "2 documents" in index
        assert "2 of 2" not in index

    def test_the_index_reflows_instead_of_scrolling_sideways(self) -> None:
        """A four-column table needed 426px at a 390px viewport.

        Asserting on the mechanism rather than on pixels: a grid list with a
        single-column breakpoint cannot overflow the way the table did.
        """
        index = _pages()["index.html"]
        assert "<table" not in index
        assert "grid-template-columns:1fr}" in index, "no single-column breakpoint"

    def test_the_favicon_request_is_answered_without_a_network_call(self) -> None:
        """Browsers ask for /favicon.ico on every page and log a 404 without it.

        It used to be answered with an empty `data:,` — a 404 silencer that
        left the tab blank. It is the site's logo now (`test_branding.py`);
        this still pins the property that made it a data URI in the first
        place, which is that it costs no request.
        """
        assert 'rel="icon" href="data:image/' in _pages()["index.html"]

    def test_a_long_relation_list_is_open_and_last_in_the_rail(self) -> None:
        """Collapsing was the fix for relations sitting *first* in the rail:
        docir's architecture document has 21 inbound edges and they filled the
        first screen. Ordered last there is nothing below them to push away,
        so the list is open — a click to see what a document connects to is a
        click to see the thing the typed graph exists for — and the count
        rides in the heading, which is what the summary was carrying.
        """
        many = [dict(_DOCS[0])] + [
            {
                "id": f"adr-1{n:03d}",
                "title": f"Linker {n}",
                "description": "d",
                "type": "decision",
                "status": "accepted",
                "created": "2026-03-01",
                "updated": "2026-03-01",
                "body": "b",
                "related": [{"target": "adr-0001", "kind": "relates_to"}],
            }
            for n in range(9)
        ]
        page = render_site(build_site(many), title="Docs", version="1")["adr-0001.html"]
        assert "<details" not in page[page.index('class="rail"') : page.index('<main class="main"')]
        assert 'Relations <span class="n">9</span>' in page, "the count belongs in the heading"
        rail = page[page.index('class="rail"') : page.index('<main class="main"')]
        assert rail.index("Local map") < rail.index("Relations"), "the glance comes first"


class TestDocRefLinks:
    """A body citing another document by id gets a link to it.

    The id is the only identifier a document has, so it is what a body writes
    when it cites one — and written plain it published as an unlinked string of
    hex. Each case below is a place the pass must *not* fire, which is the half
    a naive regex over the rendered HTML gets wrong.

    Every assertion reads the `<main>` region: the stylesheet names the class
    too, so a whole-page substring check passes on the CSS alone.
    """

    @staticmethod
    def _main(body: str) -> str:
        docs = [dict(_DOCS[0], body=body), _DOCS[1]]
        page = render_site(build_site(docs), title="Docs", version="1")["adr-0001.html"]
        return page[page.index("<main class=") : page.index("</main>")]

    def test_a_bare_id_becomes_a_link_to_its_page(self) -> None:
        main = self._main("Superseded by adr-0002 last spring.\n")
        assert '<a class="docref" href="adr-0002.html"><code>adr-0002</code></a>' in main

    def test_an_id_in_a_code_span_becomes_the_same_link(self) -> None:
        """Both spellings mean the same document, so both must read the same."""
        assert self._main("Superseded by `adr-0002`.\n") == self._main("Superseded by adr-0002.\n")

    def test_an_id_no_document_claims_is_left_alone(self) -> None:
        """Membership does the real work — the shape pattern only nominates."""
        main = self._main("Compare adr-9999 and docs-schema and foo-bar here.\n")
        assert "docref" not in main
        assert "adr-9999" in main and "foo-bar" in main

    def test_an_id_inside_a_code_block_is_not_linked(self) -> None:
        main = self._main("```\ndocir get adr-0002\n```\n")
        assert "docref" not in main

    def test_an_id_that_is_already_a_link_is_not_nested(self) -> None:
        main = self._main("[adr-0002](https://elsewhere.test) is external.\n")
        assert "docref" not in main
        assert 'href="https://elsewhere.test"' in main

    def test_surrounding_prose_survives(self) -> None:
        main = self._main("Both adr-0002 and adr-0002 apply, unlike foo-bar.\n")
        assert main.count('class="docref" href="adr-0002.html"') == 2
        assert "apply, unlike foo-bar." in main

    def test_a_document_does_not_link_to_itself(self) -> None:
        """A self-link reads as a live cross-reference and goes nowhere."""
        main = self._main("This is adr-0001, for the record.\n")
        assert 'class="docref" href="adr-0001.html"' not in main
