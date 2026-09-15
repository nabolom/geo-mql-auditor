"""Parser HTML basado en html.parser con un árbol ligero de nodos.

Sustituye el enfoque de expresiones regulares de la referencia: permite separar
contenido principal de navegación, pie y barras laterales, y extraer
encabezados, listas, tablas, enlaces, metas, JSON-LD y formularios.
"""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any, Iterator

BLOQUE = {
    "address", "article", "aside", "blockquote", "body", "caption", "dd", "details", "dialog",
    "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
    "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "summary", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul", "br",
}
VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
SIN_TEXTO = {"script", "style", "template", "svg", "head", "iframe", "object", "canvas", "select", "option", "textarea", "noscript", "title"}
BOILERPLATE_ETIQUETAS = {"nav", "header", "footer", "aside"}
BOILERPLATE_ROLES = {"navigation", "banner", "contentinfo", "complementary", "menu", "menubar", "search"}
BOILERPLATE_CLASES_RE = re.compile(
    r"(^|[\s_-])(nav|navbar|menu|footer|header|sidebar|cookie|breadcrumb|breadcrumbs|topbar|masthead|site-header|site-footer|offcanvas|megamenu)([\s_-]|$)",
    re.IGNORECASE,
)
_ESPACIOS_RE = re.compile(r"[ \t\r\f\v]+")
_SALTOS_RE = re.compile(r"\n\s*\n+")
_ORACION_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑÜ¿¡\"“(\[0-9])")
_PALABRA_RE = re.compile(r"[\wÁÉÍÓÚÑÜáéíóúñü'’\-]+", re.UNICODE)


class Nodo:
    __slots__ = ("etiqueta", "atributos", "hijos", "padre", "texto")

    def __init__(self, etiqueta: str | None, atributos: dict[str, str] | None = None, texto: str = "") -> None:
        self.etiqueta = etiqueta
        self.atributos = atributos or {}
        self.hijos: list[Nodo] = []
        self.padre: Nodo | None = None
        self.texto = texto

    @property
    def es_texto(self) -> bool:
        return self.etiqueta is None

    def atributo(self, nombre: str, defecto: str = "") -> str:
        return self.atributos.get(nombre, defecto)

    def clases(self) -> str:
        return f"{self.atributo('class')} {self.atributo('id')}"

    def ancestros(self) -> Iterator["Nodo"]:
        n = self.padre
        while n is not None:
            yield n
            n = n.padre

    def descendientes(self) -> Iterator["Nodo"]:
        pila = list(reversed(self.hijos))
        while pila:
            n = pila.pop()
            yield n
            pila.extend(reversed(n.hijos))

    def buscar(self, etiqueta: str | set[str] | None = None, **atributos: str) -> list["Nodo"]:
        etiquetas = {etiqueta} if isinstance(etiqueta, str) else etiqueta
        out = []
        for n in self.descendientes():
            if n.es_texto:
                continue
            if etiquetas and n.etiqueta not in etiquetas:
                continue
            ok = True
            for k, v in atributos.items():
                k = k.rstrip("_")
                if v is None:
                    if k not in n.atributos:
                        ok = False
                        break
                elif n.atributos.get(k, "").lower() != v.lower():
                    ok = False
                    break
            if ok:
                out.append(n)
        return out

    def primero(self, etiqueta: str | set[str] | None = None, **atributos: str) -> "Nodo | None":
        r = self.buscar(etiqueta, **atributos)
        return r[0] if r else None

    def es_boilerplate(self) -> bool:
        for n in [self, *self.ancestros()]:
            if n.etiqueta in BOILERPLATE_ETIQUETAS:
                return True
            if n.atributo("role").lower() in BOILERPLATE_ROLES:
                return True
            if n.etiqueta in ("div", "section", "ul", "ol") and BOILERPLATE_CLASES_RE.search(n.clases()):
                return True
        return False

    def __repr__(self) -> str:  # pragma: no cover
        if self.es_texto:
            return f"Texto({self.texto[:30]!r})"
        return f"<{self.etiqueta} {self.atributos}>"


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raiz = Nodo("[raiz]")
        self.pila: list[Nodo] = [self.raiz]

    def _abrir(self, tag: str, attrs: list[tuple[str, str | None]], vacio: bool) -> None:
        tag = tag.lower()
        if tag in BLOQUE and self.pila[-1].etiqueta == "p":
            self.pila.pop()
        if tag == "li":
            for i in range(len(self.pila) - 1, 0, -1):
                if self.pila[i].etiqueta in ("ul", "ol", "menu"):
                    break
                if self.pila[i].etiqueta == "li":
                    del self.pila[i:]
                    break
        if tag in ("td", "th"):
            for i in range(len(self.pila) - 1, 0, -1):
                if self.pila[i].etiqueta == "tr":
                    break
                if self.pila[i].etiqueta in ("td", "th"):
                    del self.pila[i:]
                    break
        if tag == "tr":
            for i in range(len(self.pila) - 1, 0, -1):
                if self.pila[i].etiqueta in ("table", "thead", "tbody", "tfoot"):
                    break
                if self.pila[i].etiqueta == "tr":
                    del self.pila[i:]
                    break
        nodo = Nodo(tag, {k.lower(): (v if v is not None else "") for k, v in attrs})
        nodo.padre = self.pila[-1]
        self.pila[-1].hijos.append(nodo)
        if not vacio and tag not in VACIOS:
            self.pila.append(nodo)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._abrir(tag, attrs, vacio=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._abrir(tag, attrs, vacio=True)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for i in range(len(self.pila) - 1, 0, -1):
            if self.pila[i].etiqueta == tag:
                del self.pila[i:]
                return

    def handle_data(self, data: str) -> None:
        if not data:
            return
        nodo = Nodo(None, texto=data)
        nodo.padre = self.pila[-1]
        self.pila[-1].hijos.append(nodo)


def parsear(html: str) -> Nodo:
    p = _Parser()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 - html.parser puede fallar con entradas raras
        pass
    return p.raiz


def limpiar_espacios(texto: str) -> str:
    texto = _ESPACIOS_RE.sub(" ", texto)
    texto = re.sub(r" ?\n ?", "\n", texto)
    texto = _SALTOS_RE.sub("\n", texto)
    return texto.strip()


def texto_de(nodo: Nodo, *, excluir_boilerplate: bool = False, con_saltos: bool = True) -> str:
    """Texto visible de un nodo: omite script/style/etc. y opcionalmente el boilerplate."""
    partes: list[str] = []

    def rec(n: Nodo) -> None:
        if n.es_texto:
            partes.append(n.texto)
            return
        if n.etiqueta in SIN_TEXTO:
            return
        if excluir_boilerplate and n is not nodo and (
            n.etiqueta in BOILERPLATE_ETIQUETAS
            or n.atributo("role").lower() in BOILERPLATE_ROLES
            or (n.etiqueta in ("div", "section", "ul", "ol") and BOILERPLATE_CLASES_RE.search(n.clases()))
        ):
            return
        if n.etiqueta == "img" and n.atributo("alt"):
            return
        bloque = n.etiqueta in BLOQUE
        if bloque and con_saltos:
            partes.append("\n")
        for h in n.hijos:
            rec(h)
        if bloque and con_saltos:
            partes.append("\n")
        elif not bloque:
            partes.append(" ")

    rec(nodo)
    return limpiar_espacios("".join(partes))


def contar_palabras(texto: str) -> int:
    return len(_PALABRA_RE.findall(texto))


def oraciones(texto: str) -> list[str]:
    out: list[str] = []
    for parrafo in texto.split("\n"):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        for o in _ORACION_RE.split(parrafo):
            o = o.strip()
            if o:
                out.append(o)
    return out


class Documento:
    """Vista de alto nivel sobre una página HTML."""

    def __init__(self, html: str, url: str = "") -> None:
        self.html = html or ""
        self.url = url
        self.raiz = parsear(self.html)
        self._principal: Nodo | None = None
        self._metas: dict[str, str] | None = None

    # ------------------------------------------------------------------ básicos
    def buscar(self, etiqueta: str | set[str] | None = None, **atributos: str) -> list[Nodo]:
        return self.raiz.buscar(etiqueta, **atributos)

    @property
    def body(self) -> Nodo:
        return self.raiz.primero("body") or self.raiz

    @property
    def titulo(self) -> str:
        t = self.raiz.primero("title")
        return limpiar_espacios("".join(h.texto for h in t.descendientes() if h.es_texto)) if t else ""

    @property
    def lang(self) -> str:
        h = self.raiz.primero("html")
        return (h.atributo("lang") if h else "").strip().lower()

    def metas(self) -> dict[str, str]:
        if self._metas is None:
            m: dict[str, str] = {}
            for n in self.buscar("meta"):
                clave = (n.atributo("name") or n.atributo("property") or n.atributo("http-equiv")).lower().strip()
                if clave and clave not in m:
                    m[clave] = n.atributo("content").strip()
            self._metas = m
        return self._metas

    def meta(self, clave: str) -> str:
        return self.metas().get(clave.lower(), "")

    @property
    def canonical(self) -> str | None:
        for n in self.buscar("link"):
            if "canonical" in n.atributo("rel").lower().split():
                return n.atributo("href").strip() or None
        return None

    def hreflang(self) -> list[dict[str, str]]:
        out = []
        for n in self.buscar("link"):
            if "alternate" in n.atributo("rel").lower().split() and n.atributo("hreflang"):
                out.append({"lang": n.atributo("hreflang").strip().lower(), "href": n.atributo("href").strip()})
        return out

    def robots_meta(self) -> dict[str, list[str]]:
        """Directivas de meta robots por agente (robots, googlebot, bingbot)."""
        out: dict[str, list[str]] = {}
        for n in self.buscar("meta"):
            nombre = n.atributo("name").lower().strip()
            if nombre in ("robots", "googlebot", "googlebot-news", "bingbot"):
                directivas = [d.strip().lower() for d in n.atributo("content").split(",") if d.strip()]
                out.setdefault(nombre, []).extend(directivas)
        return out

    # --------------------------------------------------------------- principal
    def _puntaje_texto(self, n: Nodo) -> int:
        total = 0
        for d in n.descendientes():
            if d.es_texto and d.padre is not None and d.padre.etiqueta not in SIN_TEXTO:
                if any(a.etiqueta == "a" for a in d.ancestros()):
                    continue
                if any(a.etiqueta in SIN_TEXTO for a in d.ancestros()):
                    continue
                total += len(d.texto.strip())
        return total

    @property
    def principal(self) -> Nodo:
        """Nodo que contiene el contenido principal (main, article o el bloque más denso)."""
        if self._principal is not None:
            return self._principal
        candidato = self.raiz.primero("main") or self.raiz.primero(None, role="main")
        total_body = self._puntaje_texto(self.body)
        if candidato is not None and total_body and self._puntaje_texto(candidato) < 0.3 * total_body:
            candidato = None  # <main> cascarón (Drupal, SPA): el contenido real está fuera
        if candidato is None:
            articulos = [a for a in self.buscar("article") if not a.es_boilerplate()]
            if articulos:
                mejor = max(articulos, key=self._puntaje_texto)
                if total_body and self._puntaje_texto(mejor) >= 0.3 * total_body:
                    candidato = mejor
        if candidato is None:
            actual = self.body
            while True:
                hijos = [
                    h for h in actual.hijos
                    if not h.es_texto and h.etiqueta not in SIN_TEXTO and not h.es_boilerplate()
                ]
                if not hijos:
                    break
                puntajes = [(self._puntaje_texto(h), h) for h in hijos]
                total = sum(p for p, _ in puntajes)
                if total == 0:
                    break
                mejor_p, mejor = max(puntajes, key=lambda x: x[0])
                if mejor_p / total >= 0.7 and mejor.etiqueta in ("div", "section", "article", "main", "td", "body", "form"):
                    actual = mejor
                    continue
                break
            candidato = actual
        self._principal = candidato
        return candidato

    def texto(self, *, excluir_boilerplate: bool = True) -> str:
        return texto_de(self.body, excluir_boilerplate=excluir_boilerplate)

    def texto_principal(self) -> str:
        return texto_de(self.principal, excluir_boilerplate=True)

    def texto_noscript(self) -> str:
        return limpiar_espacios(" ".join(
            "".join(h.texto for h in n.descendientes() if h.es_texto) for n in self.buscar("noscript")
        ))

    # --------------------------------------------------------------- estructura
    def encabezados(self, *, solo_principal: bool = False) -> list[dict[str, Any]]:
        raiz = self.principal if solo_principal else self.body
        out = []
        for n in raiz.buscar({"h1", "h2", "h3", "h4", "h5", "h6"}):
            texto = texto_de(n, con_saltos=False)
            if not texto:
                continue
            out.append({
                "nivel": int(n.etiqueta[1]),
                "texto": texto,
                "en_principal": self._dentro(n, self.principal),
                "boilerplate": n.es_boilerplate(),
            })
        return out

    def parrafos(self, *, solo_principal: bool = True) -> list[str]:
        raiz = self.principal if solo_principal else self.body
        out = []
        for n in raiz.buscar("p"):
            if n.es_boilerplate():
                continue
            t = texto_de(n, con_saltos=False)
            if t:
                out.append(t)
        return out

    def listas(self, *, solo_principal: bool = True) -> dict[str, int]:
        raiz = self.principal if solo_principal else self.body
        ul = [n for n in raiz.buscar("ul") if not n.es_boilerplate()]
        ol = [n for n in raiz.buscar("ol") if not n.es_boilerplate()]
        items = sum(len([h for h in n.hijos if h.etiqueta == "li"]) for n in ul + ol)
        dl = [n for n in raiz.buscar("dl") if not n.es_boilerplate()]
        return {"ul": len(ul), "ol": len(ol), "items": items, "dl": len(dl)}

    def tablas(self, *, solo_principal: bool = True) -> list[dict[str, Any]]:
        raiz = self.principal if solo_principal else self.body
        out = []
        for t in raiz.buscar("table"):
            if t.es_boilerplate():
                continue
            filas = t.buscar("tr")
            columnas = max((len([c for c in f.hijos if c.etiqueta in ("td", "th")]) for f in filas), default=0)
            out.append({
                "filas": len(filas),
                "columnas": columnas,
                "con_encabezado": bool(t.buscar("th")) or bool(t.buscar("thead")),
                "caption": texto_de(t.primero("caption"), con_saltos=False) if t.primero("caption") else "",
            })
        return out

    def enlaces(self) -> list[dict[str, Any]]:
        out = []
        for a in self.buscar("a"):
            href = a.atributo("href").strip()
            if not href:
                continue
            out.append({
                "href": href,
                "texto": texto_de(a, con_saltos=False)[:200],
                "rel": a.atributo("rel").lower(),
                "en_principal": self._dentro(a, self.principal),
                "boilerplate": a.es_boilerplate(),
                "nodo": a,
            })
        return out

    def imagenes(self) -> list[dict[str, Any]]:
        return [
            {"src": n.atributo("src") or n.atributo("data-src"), "alt": n.atributo("alt"), "en_principal": self._dentro(n, self.principal)}
            for n in self.buscar("img")
        ]

    def times(self) -> list[dict[str, str]]:
        return [
            {"datetime": n.atributo("datetime").strip(), "texto": texto_de(n, con_saltos=False), "en_principal": self._dentro(n, self.principal)}
            for n in self.buscar("time")
        ]

    def json_ld(self) -> list[dict[str, Any]]:
        out = []
        for s in self.buscar("script"):
            if "ld+json" not in s.atributo("type").lower():
                continue
            crudo = "".join(h.texto for h in s.descendientes() if h.es_texto).strip()
            if not crudo:
                continue
            try:
                datos = json.loads(crudo)
                out.append({"crudo": crudo, "datos": datos, "error": None})
            except json.JSONDecodeError as e:
                out.append({"crudo": crudo, "datos": None, "error": f"{e.msg} (línea {e.lineno}, columna {e.colno})"})
        return out

    def formularios(self) -> list[dict[str, Any]]:
        out = []
        for f in self.buscar("form"):
            campos = []
            for c in f.buscar({"input", "select", "textarea"}):
                tipo = c.atributo("type").lower() or c.etiqueta
                campos.append({"name": c.atributo("name"), "type": tipo, "oculto": tipo == "hidden"})
            out.append({
                "action": f.atributo("action"),
                "method": f.atributo("method").lower() or "get",
                "id": f.atributo("id"),
                "clases": f.atributo("class"),
                "campos": campos,
                "en_principal": self._dentro(f, self.principal),
            })
        return out

    def scripts_src(self) -> list[str]:
        return [s.atributo("src") for s in self.buscar("script") if s.atributo("src")]

    def scripts_inline(self) -> str:
        return "\n".join(
            "".join(h.texto for h in s.descendientes() if h.es_texto)
            for s in self.buscar("script") if not s.atributo("src")
        )

    def botones(self) -> list[dict[str, Any]]:
        out = []
        for n in self.buscar({"button", "a", "input"}):
            if n.etiqueta == "input" and n.atributo("type").lower() not in ("submit", "button"):
                continue
            if n.etiqueta == "a":
                clases = n.clases().lower()
                if not any(k in clases for k in ("btn", "button", "cta")):
                    continue
            texto = n.atributo("value") if n.etiqueta == "input" else texto_de(n, con_saltos=False)
            if texto:
                out.append({"texto": texto[:120], "href": n.atributo("href"), "boilerplate": n.es_boilerplate()})
        return out

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _dentro(n: Nodo, contenedor: Nodo) -> bool:
        return n is contenedor or any(a is contenedor for a in n.ancestros())

    def resumen(self) -> dict[str, Any]:
        tp = self.texto_principal()
        return {
            "titulo": self.titulo,
            "lang": self.lang,
            "palabras_total": contar_palabras(self.texto(excluir_boilerplate=False)),
            "palabras_principal": contar_palabras(tp),
            "encabezados": len(self.encabezados()),
            "json_ld": len(self.json_ld()),
            "formularios": len(self.formularios()),
        }
