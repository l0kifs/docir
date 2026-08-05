"""Code-block colouring — five roles, and the two rules that keep it honest.

Every assertion here is one of: the right role for the right token, or a case
where a naive highlighter asserts a structure that is not in the source. The
second kind is the point — a wrong colour is worse than no colour, because it
reads as a claim about the code.
"""

from __future__ import annotations

from docir.modules.publishing.infra.highlight import highlight, language_label


class TestLabel:
    def test_the_fence_word_is_the_label(self) -> None:
        assert language_label("bash") == "bash"
        assert language_label("  Python  hl_lines=1") == "python"

    def test_an_unlabelled_fence_reads_as_text(self) -> None:
        assert language_label("") == "text"


class TestShell:
    def test_command_then_subcommand_then_arguments(self) -> None:
        """The interesting word in a docs snippet is the tool's own name,
        which no keyword list can contain — position is the signal."""
        out = highlight("docir get adr-1 --json", "bash")
        assert '<span class="sy-fn">docir</span>' in out
        assert '<span class="sy-kw">get</span>' in out
        assert '<span class="sy-flag">--json</span>' in out
        assert ">adr-1<" not in out, "a positional argument carries no role"

    def test_a_pipe_starts_a_new_command(self) -> None:
        out = highlight("gh release list | cat", "sh")
        assert out.count('class="sy-fn"') == 2

    def test_each_line_starts_a_new_command(self) -> None:
        out = highlight("cd src\nuv run pytest", "bash")
        assert '<span class="sy-fn">cd</span>' in out
        assert '<span class="sy-fn">uv</span>' in out

    def test_a_hash_inside_a_string_is_not_a_comment(self) -> None:
        """Comments and strings are matched in one alternation, so whichever
        opens first wins — the rule the whole file rests on."""
        out = highlight('echo "value # not a comment"', "bash")
        assert '<span class="sy-str">&quot;value # not a comment&quot;</span>' in out
        assert "sy-cmt" not in out

    def test_a_quote_inside_a_comment_does_not_open_a_string(self) -> None:
        out = highlight("# it's fine", "bash")
        assert out == '<span class="sy-cmt"># it&#x27;s fine</span>'


class TestOtherLanguages:
    def test_python_names_what_def_defines(self) -> None:
        out = highlight("def render(x):\n    return x", "python")
        assert '<span class="sy-kw">def</span>' in out
        assert '<span class="sy-fn">render</span>' in out
        assert '<span class="sy-kw">return</span>' in out

    def test_yaml_keys_literals_and_comments(self) -> None:
        out = highlight("profiles:\n  - software  # default\nstrict: true", "yml")
        assert '<span class="sy-fn">profiles</span>' in out
        assert '<span class="sy-cmt"># default</span>' in out
        assert '<span class="sy-kw">true</span>' in out

    def test_json_separates_keys_from_string_values(self) -> None:
        out = highlight('{"id": "adr-1", "stale": false}', "json")
        assert '<span class="sy-fn">&quot;id&quot;</span>' in out
        assert '<span class="sy-str">&quot;adr-1&quot;</span>' in out
        assert '<span class="sy-kw">false</span>' in out

    def test_sql_keywords_are_case_insensitive(self) -> None:
        out = highlight("SELECT id FROM documents -- all of them", "sql")
        assert '<span class="sy-kw">SELECT</span>' in out
        assert '<span class="sy-cmt">-- all of them</span>' in out

    def test_toml_sections_and_keys(self) -> None:
        out = highlight('[project]\nversion = "0.2.0"  # bump', "toml")
        assert '<span class="sy-flag">[project]</span>' in out
        assert '<span class="sy-fn">version</span>' in out
        assert '<span class="sy-cmt"># bump</span>' in out


class TestRefusals:
    def test_an_unknown_language_is_left_alone(self) -> None:
        """`#` is a comment in five languages and an operator in others.
        Guessing paints a structure that is not there."""
        assert highlight("# not a comment", "brainfuck") == "# not a comment"
        assert highlight("x = 1", "") == "x = 1"

    def test_every_path_escapes(self) -> None:
        """A body is untrusted input to the renderer even from the store."""
        assert "<script>" not in highlight("<script>alert(1)</script>", "bash")
        assert "<script>" not in highlight("<script>alert(1)</script>", "nolang")

    def test_an_unterminated_quote_does_not_swallow_the_block(self) -> None:
        """A single-line string form: a stray quote costs one line's colour,
        not every line after it."""
        out = highlight('echo "oops\ndocir check', "bash")
        assert '<span class="sy-fn">docir</span>' in out
