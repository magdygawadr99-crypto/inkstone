from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, include, this, using, words
from ..registry import register
from ..token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
    Whitespace,
)

# One logical line of shell: backslash-newline continues it, and so do
# comment-only lines in the middle of a continued RUN.
_SHELL_LINE = r"(?:[^\\\n]|\\.|\\\n(?:[ \t]*#.*\n)*)+"
_DOCKER_VARIABLE = r"\$(?:\{[^}\n]*\}|[a-zA-Z_]\w*)"


@register
class DockerfileLexer(RegexLexer):
    name = "dockerfile"
    aliases = ("docker", "containerfile")
    extensions = (".dockerfile",)
    filenames = ("Dockerfile", "Dockerfile.*", "Containerfile", "Containerfile.*")

    flags = re.MULTILINE | re.IGNORECASE

    # Root only ever sees the start of an instruction: each one pushes a
    # state that eats the rest of its (logical) line.
    # TODO: BuildKit heredocs (RUN <<EOF ... EOF). The body currently falls
    # through to root and comes out as plain text, line by line.
    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"#\s*(?:syntax|escape|check)\s*=.*$", Comment.Preproc),
            (r"#.*$", Comment.Single),
            (r"ONBUILD\b", Keyword),
            (r"FROM\b", Keyword, "from"),
            # exec form: CMD ["nginx", "-g", "daemon off;"]
            (
                r"(RUN|CMD|ENTRYPOINT|SHELL|VOLUME)([ \t]+)(\[.*\])(?=[ \t]*$)",
                bygroups(Keyword, Whitespace, using("json")),
            ),
            (r"(?:RUN|CMD|ENTRYPOINT)\b", Keyword, "shell"),
            (r"(?:ENV|ARG|LABEL)\b", Keyword, "pairs"),
            (r"HEALTHCHECK\b", Keyword, "healthcheck"),
            (
                r"(?:ADD|COPY|EXPOSE|MAINTAINER|SHELL|STOPSIGNAL|USER|VOLUME"
                r"|WORKDIR)\b",
                Keyword,
                "arguments",
            ),
            (r".+$", Text),
        ],
        "line": [
            (r"[ \t]+", Whitespace),
            (r"\\\n", String.Escape),
            (r"\n", Whitespace, "#pop"),
            (r"--[\w-]+", Name.Attribute),
            (_DOCKER_VARIABLE, Name.Variable),
            (r'"', String, "string"),
            (r"'[^'\n]*'", String),
        ],
        "from": [
            include("line"),
            (r"AS\b", Keyword),
            (r"(?<=\bAS\s)[\w.-]+", Name.Label),
            (r"=", Operator),
            (r"[^\s$\"'=]+", String),
        ],
        "shell": [
            (r"[ \t]+", Whitespace),
            (r"(--[\w-]+)(=)(\S+)", bygroups(Name.Attribute, Operator, String)),
            (_SHELL_LINE, using("bash"), "#pop"),
            (r"\n", Whitespace, "#pop"),
        ],
        "pairs": [
            include("line"),
            (r"([\w.-]+)(=)", bygroups(Name.Variable, Operator)),
            # "ARG NAME" with no default, and the legacy "ENV key value"
            (r"(?<=ENV\s|ARG\s)[\w.-]+", Name.Variable),
            (r"[^\s$\"'\\]+", String),
            (r"\\", String),
        ],
        "healthcheck": [
            include("line"),
            (r"CMD(?=[ \t])", Keyword, ("#pop", "shell")),
            (r"NONE\b", Keyword),
            (r"=", Operator),
            (r"[^\s$\"'=\\]+", Text),
            (r"\\", Text),
        ],
        "arguments": [
            include("line"),
            (r"=", Operator),
            (r"(\d+)(/)(tcp|udp)\b", bygroups(Number, Punctuation, Keyword)),
            (r"\d+(?![\w.])", Number),
            (r"[\[\],]", Punctuation),
            (r"[^\s$\"'=\[\],\\]+", Text),
            (r"\\", Text),
        ],
        "string": [
            (r'"', String, "#pop"),
            (r"\\.", String.Escape),
            (_DOCKER_VARIABLE, Name.Variable),
            (r'[^"\\$\n]+', String),
            (r"\$", String),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        if not re.search(r"^FROM\s+\S+", code, re.M):
            return 0.0
        if re.search(r"^(?:RUN|CMD|COPY|ENTRYPOINT|WORKDIR|EXPOSE)\s", code, re.M):
            return 0.85
        return 0.4


_MAKE_FUNCTIONS = """
    abspath addprefix addsuffix and basename call dir error eval file filter
    filter-out findstring firstword flavor foreach if info join lastword
    notdir or origin patsubst realpath shell sort strip subst suffix value
    warning wildcard word wordlist words
""".split()

_MAKE_DIRECTIVES = """
    -include define else endef endif export ifdef ifeq ifndef ifneq include
    override private sinclude undefine unexport vpath
""".split()


@register
class MakefileLexer(RegexLexer):
    name = "makefile"
    aliases = ("make", "mk", "mf", "gnumake")
    extensions = (".mk", ".mak")
    filenames = ("Makefile", "makefile", "GNUmakefile", "Makefile.*")

    tokens = {
        "root": [
            (r"^(\t)([@+-]*)", bygroups(Whitespace, Operator), "recipe"),
            (r"\n", Whitespace),
            (r"[ \t]+", Whitespace),
            (r"#(?:[^\\\n]|\\.|\\\n)*", Comment.Single),
            # define NAME ... endef: the body is opaque until it's expanded
            (
                r"^(define)([ \t]+)([^\s:=+?!#]+)(.*\n)((?:.*\n)*?)(endef)(?![\w.-])",
                bygroups(Keyword, Whitespace, Name.Variable, None, String, Keyword),
            ),
            (
                words(_MAKE_DIRECTIVES, prefix=r"(?<![\w.-])", suffix=r"(?![\w.-])"),
                Keyword,
            ),
            (
                r"([\w.-]+)([ \t]*)(::?:?=|[?+!]?=)",
                bygroups(Name.Variable, Whitespace, Operator),
                "value",
            ),
            # target: prerequisites
            (
                r"^([^\s:=#](?:[^:=#\n]*[^\s:=#])?)([ \t]*)(::?)(?![:=])",
                bygroups(using(this, state="targets"), Whitespace, Punctuation),
                "prerequisites",
            ),
            include("expansions"),
            (r"[^\s$#\\]+", Text),
            (r"\\\n", String.Escape),
            (r"[\\$]", Text),
        ],
        "targets": [
            (r"[ \t]+", Whitespace),
            (r"\.[A-Z_]+(?![\w.])", Name.Builtin),
            include("expansions"),
            (r"[^\s$]+", Name.Function),
        ],
        "expansions": [
            # $$ is how a recipe says $ to the shell
            (r"\$\$(?:[a-zA-Z_]\w*|\{[^}\n]*\}|[?@*#!$0-9])?", Name.Variable),
            (r"\$[@%<?^+*|]|\$\([@%<?^+*][DF]\)", Name.Variable.Magic),
            (
                rf"(\$[({{])({words(_MAKE_FUNCTIONS)})(\s+)",
                bygroups(Keyword, Name.Builtin, Whitespace),
                "expansion",
            ),
            (r"(\$[({])([\w.-]+)([)}])", bygroups(Keyword, Name.Variable, Keyword)),
            (r"\$[({]", Keyword, "expansion"),
            (r"\$[a-zA-Z_]", Name.Variable),
        ],
        # inside $(...): function arguments or a substitution reference
        "expansion": [
            (r"[)}]", Keyword, "#pop"),
            (r"[({]", Text, "nested"),
            (r",", Punctuation),
            include("expansions"),
            (r"[^$(){},\\]+", Text),
            (r"[\\$]", Text),
        ],
        "nested": [
            (r"[)}]", Text, "#pop"),
            (r"[({]", Text, "#push"),
            include("expansions"),
            (r"[^$(){}\\]+", Text),
            (r"[\\$]", Text),
        ],
        "value": [
            (r"\\\n", String.Escape),
            (r"\n", Whitespace, "#pop"),
            (r"[ \t]+", Whitespace),
            (r"(?<=\s)#.*$", Comment.Single),
            include("expansions"),
            (r"[^\s$#\\]+", Text),
            (r"[#\\$]", Text),
        ],
        "prerequisites": [
            (r"\\\n", String.Escape),
            (r"\n", Whitespace, "#pop"),
            (r"[ \t]+", Whitespace),
            (r"#.*$", Comment.Single),
            (r"\|", Operator),
            # "target: deps ; command" puts the recipe on the same line
            (r";", Punctuation, ("#pop", "recipe")),
            include("expansions"),
            (r"[^\s$#\\|;]+", Text),
            (r"[\\$]", Text),
        ],
        # A recipe line is shell, but with make's own $(...) on top, so it
        # gets a light treatment here rather than a trip through the bash
        # lexer, which would read $(OBJS) as command substitution.
        "recipe": [
            (r"\\\n", String.Escape),
            (r"\n", Whitespace, "#pop"),
            (r"[ \t]+", Whitespace),
            (r"(?<=\s)#.*$", Comment.Single),
            include("expansions"),
            (r'"', String, "recipe-string"),
            (r"'[^'\n]*'", String),
            (r"&&|\|\||[|;&<>]", Operator),
            (r"[^\s$\"'#\\|;&<>]+", Text),
            (r"[#\\$]", Text),
        ],
        "recipe-string": [
            (r'"', String, "#pop"),
            (r"\\.", String.Escape),
            include("expansions"),
            (r'[^"\\$\n]+', String),
            (r"[\\$]", String),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        if re.search(r"^\.PHONY\s*:", code, re.M):
            return 0.9
        if re.search(r"^[\w./%-]+\s*:(?!=).*\n\t\S", code, re.M):
            return 0.7 if re.search(r"\$[(@<^]", code) else 0.5
        return 0.0
