"""Collectors for general-website content evidence."""

from __future__ import annotations

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.extraction.types import EvidenceUnit


class ContentCollectors:
    """Collect rule-grounded evidence candidates from general websites."""

    SOCIAL_LABELS = {
        "linkedin",
        "mastodon",
        "twitter",
        "x",
        "facebook",
        "instagram",
        "youtube",
        "discord",
        "slack",
        "telegram",
        "reddit",
    }

    SOCIAL_DOMAINS = (
        "linkedin.com",
        "twitter.com",
        "x.com",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "youtu.be",
        "mastodon",
        "discord.",
        "slack.com",
        "t.me",
        "reddit.com",
    )

    AUTH_LABEL_FRAGMENTS: tuple[str, ...] = ()
    CTA_HINT_FRAGMENTS: tuple[str, ...] = ()
    PROMINENT_CLASS_HINTS: tuple[str, ...] = ()
    SECTION_CONTAINER_HINTS: tuple[str, ...] = ()

    def collect(self, soup: BeautifulSoup, url: str, page_type: str, screenshot_ref: str = "") -> list[EvidenceUnit]:
        units: list[EvidenceUnit] = []
        units.extend(self._collect_hero_units(soup, url, page_type, screenshot_ref))
        units.extend(self._collect_cta_units(soup, url, page_type, screenshot_ref))
        units.extend(self._collect_nav_units(soup, url, page_type, screenshot_ref))
        units.extend(self._collect_section_units(soup, url, page_type, screenshot_ref))
        return units

    def _is_low_value_nav_label(self, label: str) -> bool:
        return not " ".join(label.lower().split())

    def _is_low_value_nav_href(self, href: str) -> bool:
        normalized = href.strip().lower()
        if not normalized:
            return True
        if normalized in {"#", "javascript:;"}:
            return True
        if normalized.startswith("#"):
            return True
        return False

    def _is_social_nav_candidate(self, label: str, href: str) -> bool:
        normalized_label = " ".join(label.lower().split())
        if normalized_label in self.SOCIAL_LABELS:
            return True
        normalized_href = href.strip().lower()
        return any(domain in normalized_href for domain in self.SOCIAL_DOMAINS)

    def _is_auth_nav_candidate(self, label: str, href: str) -> bool:
        return False

    def _node_hint_text(self, node: Tag) -> str:
        parts: list[str] = [node.name]
        parts.extend(str(cls) for cls in node.get("class", []) if cls)
        if node.get("id"):
            parts.append(str(node.get("id")))
        if node.get("role"):
            parts.append(str(node.get("role")))
        if node.get("aria-label"):
            parts.append(str(node.get("aria-label")))
        return " ".join(parts).lower()

    def _ancestor_hint_text(self, node: Tag, depth: int = 3) -> str:
        parts: list[str] = []
        current: Tag | None = node
        for _ in range(depth):
            current = current.parent if isinstance(current.parent, Tag) else None
            if current is None:
                break
            parts.append(self._node_hint_text(current))
        return " ".join(parts)

    def _has_hint(self, text: str, hints: tuple[str, ...]) -> bool:
        return any(hint in text for hint in hints)

    def _clean_text(self, text: str) -> str:
        return " ".join(text.split())

    def _cta_score(self, node: Tag, label: str, href: str, selector: str) -> float:
        normalized_label = " ".join(label.lower().split())
        score = 0.0

        if node.name == "button":
            score += 2.5
        if selector.startswith("main") or selector.startswith("[role='main']"):
            score += 1.5
        elif selector.startswith("header"):
            score += 0.5
        if href and not self._is_low_value_nav_href(href):
            score += 0.5
        if 1 <= len(normalized_label.split()) <= 6:
            score += 0.8
        if len(normalized_label) <= 48:
            score += 0.5
        return score

    def _collect_hero_units(self, soup: BeautifulSoup, url: str, page_type: str, screenshot_ref: str) -> list[EvidenceUnit]:
        selectors = [
            "main h1",
            "header h1",
            "[role='main'] h1",
            ".hero h1",
            ".hero-title",
            "section h1",
        ]
        units: list[EvidenceUnit] = []
        seen: set[str] = set()
        for selector in selectors:
            for node in soup.select(selector)[:4]:
                text = node.get_text(" ", strip=True)
                if not text or text in seen:
                    continue
                seen.add(text)
                units.append(self._make_unit(
                    node=node,
                    kind="hero",
                    role="page_value_prop",
                    raw_text=text,
                    url=url,
                    page_type=page_type,
                    screenshot_ref=screenshot_ref,
                    confidence=0.82,
                    tags=["content", "hero"],
                    metadata={"selector": selector},
                ))
        return units[:4]

    def _collect_cta_units(self, soup: BeautifulSoup, url: str, page_type: str, screenshot_ref: str) -> list[EvidenceUnit]:
        selectors = [
            "main a",
            "main button",
            "header a",
            "[role='main'] a",
            "[role='main'] button",
        ]
        scored_units: list[tuple[float, int, EvidenceUnit]] = []
        seen: set[tuple[str, str]] = set()
        order = 0
        for selector in selectors:
            for node in soup.select(selector)[:50]:
                label = node.get_text(" ", strip=True)
                href = (node.get("href") or "").strip() if node.name == "a" else ""
                if not label or len(label) > 120:
                    continue
                if href and self._is_low_value_nav_href(href):
                    continue
                if self._is_social_nav_candidate(label, href):
                    continue
                dedupe_key = (label, href)
                if dedupe_key in seen:
                    continue
                score = self._cta_score(node, label, href, selector)
                if score < 2.2:
                    continue
                seen.add(dedupe_key)
                scored_units.append((score, order, self._make_unit(
                    node=node,
                    kind="cta",
                    role="entry_point",
                    raw_text=label,
                    url=url,
                    page_type=page_type,
                    screenshot_ref=screenshot_ref,
                    confidence=0.76,
                    tags=["actionable", "content"],
                    metadata={"href": href, "selector": selector},
                )))
                order += 1
        scored_units.sort(key=lambda item: (-item[0], item[1]))
        return [unit for _, _, unit in scored_units[:10]]

    def _collect_nav_units(self, soup: BeautifulSoup, url: str, page_type: str, screenshot_ref: str) -> list[EvidenceUnit]:
        units: list[EvidenceUnit] = []
        seen: set[tuple[str, str]] = set()
        selectors = [
            "header nav > ul > li > a",
            "header nav > div > ul > li > a",
            "nav > ul > li > a",
            "nav > div > ul > li > a",
            "[role='navigation'] > ul > li > a",
            "[role='navigation'] a",
        ]
        nav_nodes: list[Tag] = []
        seen_paths: set[str] = set()
        for selector in selectors:
            for node in soup.select(selector)[:24]:
                path = self._dom_path(node)
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                nav_nodes.append(node)

        if not nav_nodes:
            nav_nodes = list(soup.select("nav a, header nav a")[:32])

        for node in nav_nodes:
            label = node.get_text(" ", strip=True)
            href = (node.get("href") or "").strip()
            if not label or len(label) > 80:
                continue
            if self._is_low_value_nav_label(label):
                continue
            if self._is_low_value_nav_href(href):
                continue
            if self._is_social_nav_candidate(label, href):
                continue
            if self._is_auth_nav_candidate(label, href):
                continue
            dedupe_key = (label, href)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            units.append(self._make_unit(
                node=node,
                kind="nav_item",
                role="global_navigation",
                raw_text=label,
                url=url,
                page_type=page_type,
                screenshot_ref=screenshot_ref,
                confidence=0.8,
                tags=["navigation", "actionable"],
                metadata={"href": href},
            ))
        return units[:12]

    def _collect_section_units(self, soup: BeautifulSoup, url: str, page_type: str, screenshot_ref: str) -> list[EvidenceUnit]:
        scored_units: list[tuple[float, int, EvidenceUnit]] = []
        seen_titles: set[str] = set()
        order = 0

        containers = soup.select(
            "main section, article section, [role='main'] section, article, main .card, main .feature, "
            "main .content, main .box, main .panel, main .module, main .callout, main .overview"
        )
        for node in containers[:32]:
            title_node = node.select_one("h2, h3, h4, .title, .card-title, header h2, header h3")
            if not title_node:
                continue
            candidate = self._build_section_candidate(node, title_node)
            if not candidate:
                continue
            title, summary, score = candidate
            normalized_title = title.lower()
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)
            scored_units.append((score, order, self._make_unit(
                node=node,
                kind="content_section",
                role="supporting_content",
                raw_text=title,
                url=url,
                page_type=page_type,
                screenshot_ref=screenshot_ref,
                confidence=0.72,
                tags=["content", "section"],
                metadata={"summary": summary[:240]},
            )))
            order += 1

        heading_scope = soup.select("main h2, main h3, article h2, article h3, [role='main'] h2, [role='main'] h3")
        for heading in heading_scope[:32]:
            title = self._clean_text(heading.get_text(" ", strip=True))
            if not title:
                continue
            normalized_title = title.lower()
            if normalized_title in seen_titles:
                continue
            container = self._find_section_container(heading)
            if not container:
                continue
            candidate = self._build_section_candidate(container, heading)
            if not candidate:
                continue
            title, summary, score = candidate
            normalized_title = title.lower()
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)
            scored_units.append((score, order, self._make_unit(
                node=container,
                kind="content_section",
                role="supporting_content",
                raw_text=title,
                url=url,
                page_type=page_type,
                screenshot_ref=screenshot_ref,
                confidence=0.72,
                tags=["content", "section"],
                metadata={"summary": summary[:240]},
            )))
            order += 1

        scored_units.sort(key=lambda item: (-item[0], item[1]))
        return [unit for _, _, unit in scored_units[:10]]

    def collect_docs_rescue_units(self, soup: BeautifulSoup, url: str, page_type: str,
                                  screenshot_ref: str) -> list[EvidenceUnit]:
        """Collect docs-index style sections when generic section extraction is weak."""
        scored_units: list[tuple[float, int, EvidenceUnit]] = []
        seen_titles: set[str] = set()
        order = 0

        title_blocks = soup.select(
            "main p > strong, article p > strong, [role='main'] p > strong, "
            ".document .body p > strong, .documentwrapper .body p > strong"
        )
        for strong in title_blocks[:12]:
            title = self._clean_text(strong.get_text(" ", strip=True).rstrip(":"))
            if not title:
                continue
            normalized_title = title.lower()
            if normalized_title in seen_titles:
                continue
            parent = strong.parent if isinstance(strong.parent, Tag) else None
            sibling = self._next_meaningful_sibling(parent) if parent else None
            if sibling is None:
                continue
            if sibling.name not in {"table", "ul", "ol", "div"}:
                continue
            summary = self._summarize_docs_group(sibling)
            score = 2.6 if summary else 2.1
            seen_titles.add(normalized_title)
            scored_units.append((score, order, self._make_unit(
                node=sibling,
                kind="content_section",
                role="docs_navigation_section",
                raw_text=title,
                url=url,
                page_type=page_type,
                screenshot_ref=screenshot_ref,
                confidence=0.78,
                tags=["content", "section", "docs"],
                metadata={"summary": summary[:240]},
            )))
            order += 1

        for block in soup.select(
            "main p.biglink, article p.biglink, [role='main'] p.biglink, .document .body p.biglink"
        )[:24]:
            anchor = block.select_one("a.biglink, a")
            if not anchor:
                continue
            title = self._clean_text(anchor.get_text(" ", strip=True))
            if not title:
                continue
            normalized_title = title.lower()
            if normalized_title in seen_titles:
                continue
            summary_node = block.select_one(".linkdescr")
            summary = self._clean_text(summary_node.get_text(" ", strip=True)) if summary_node else ""
            seen_titles.add(normalized_title)
            scored_units.append((2.4 if summary else 2.1, order, self._make_unit(
                node=block,
                kind="content_section",
                role="docs_navigation_section",
                raw_text=title,
                url=url,
                page_type=page_type,
                screenshot_ref=screenshot_ref,
                confidence=0.76,
                tags=["content", "section", "docs"],
                metadata={"summary": summary[:240], "href": (anchor.get("href") or "").strip()},
            )))
            order += 1

        scored_units.sort(key=lambda item: (-item[0], item[1]))
        return [unit for _, _, unit in scored_units[:10]]

    def _find_section_container(self, heading: Tag) -> Tag | None:
        current: Tag | None = heading
        for _ in range(5):
            current = current.parent if isinstance(current.parent, Tag) else None
            if current is None:
                return None
            if current.name in {"section", "article"}:
                return current
            hint_text = self._node_hint_text(current)
            if self._has_hint(hint_text, self.SECTION_CONTAINER_HINTS):
                return current
            if current.name in {"main", "body"}:
                break
        parent = heading.parent if isinstance(heading.parent, Tag) else None
        return parent if parent and parent.name not in {"main", "body"} else None

    def _build_section_candidate(self, container: Tag, title_node: Tag) -> tuple[str, str, float] | None:
        title = self._clean_text(title_node.get_text(" ", strip=True))
        if not title or len(title) < 3 or len(title) > 120:
            return None
        summary = self._extract_section_summary(container, title_node)
        score = self._section_score(container, title, summary)
        if score < 2.0:
            return None
        return title, summary, score

    def _extract_section_summary(self, container: Tag, title_node: Tag) -> str:
        snippets: list[str] = []

        for selector in ("p", "li", "dd"):
            for node in container.select(selector)[:6]:
                if node is title_node or title_node in node.parents:
                    continue
                text = self._clean_text(node.get_text(" ", strip=True))
                if len(text) < 30:
                    continue
                if text not in snippets:
                    snippets.append(text)
                if sum(len(item) for item in snippets) >= 220:
                    break
            if snippets:
                break

        if not snippets:
            fallback_nodes = []
            next_sibling = title_node.next_sibling
            while next_sibling is not None and len(fallback_nodes) < 3:
                if isinstance(next_sibling, Tag):
                    fallback_nodes.append(next_sibling)
                next_sibling = next_sibling.next_sibling
            for node in fallback_nodes:
                text = self._clean_text(node.get_text(" ", strip=True))
                if len(text) >= 30 and text not in snippets:
                    snippets.append(text)

        return " ".join(snippets)[:240]

    def _summarize_docs_group(self, container: Tag) -> str:
        snippets: list[str] = []
        for node in container.select(".linkdescr, p.biglink, li, p")[:8]:
            text = self._clean_text(node.get_text(" ", strip=True))
            if len(text) < 20:
                continue
            if text not in snippets:
                snippets.append(text)
            if sum(len(item) for item in snippets) >= 220:
                break
        return " ".join(snippets)[:240]

    def _next_meaningful_sibling(self, node: Tag | None) -> Tag | None:
        current = node.next_sibling if node else None
        while current is not None:
            if isinstance(current, Tag):
                return current
            current = current.next_sibling
        return None

    def _section_score(self, container: Tag, title: str, summary: str) -> float:
        score = 0.0
        hint_text = self._node_hint_text(container)
        ancestor_hints = self._ancestor_hint_text(container)

        if container.name in {"section", "article"}:
            score += 1.4
        if self._has_hint(hint_text, self.SECTION_CONTAINER_HINTS):
            score += 1.2
        if "main" in ancestor_hints or "article" in ancestor_hints:
            score += 0.6
        if 3 <= len(title.split()) <= 10:
            score += 0.7
        if len(summary) >= 60:
            score += 1.1
        elif len(summary) >= 30:
            score += 0.6
        if container.select_one("a, button"):
            score += 0.2
        return score

    def _make_unit(
        self,
        node: Tag,
        kind: str,
        role: str,
        raw_text: str,
        url: str,
        page_type: str,
        screenshot_ref: str,
        confidence: float,
        tags: list[str],
        metadata: dict,
    ) -> EvidenceUnit:
        return EvidenceUnit(
            id=self._unit_id(kind, node),
            kind=kind,
            role=role,
            raw_text=raw_text,
            url=url,
            page_type=page_type,
            locator=self._css_locator(node),
            dom_path=self._dom_path(node),
            html_fragment=str(node)[:1200],
            screenshot_ref=screenshot_ref,
            confidence=confidence,
            source="dom_rule",
            tags=tags,
            metadata=metadata,
        )

    def _unit_id(self, kind: str, node: Tag) -> str:
        return f"{kind}:{self._dom_path(node)}"

    def _css_locator(self, node: Tag) -> str:
        if node.get("id"):
            return f"#{node.get('id')}"
        classes = [cls for cls in node.get("class", []) if cls][:2]
        if classes:
            return f"{node.name}." + ".".join(classes)
        return node.name

    def _dom_path(self, node: Tag) -> str:
        parts: list[str] = []
        current: Tag | None = node
        while current and current.name not in {"[document]", "html"}:
            parent = current.parent if isinstance(current.parent, Tag) else None
            if parent is None:
                break
            siblings = [child for child in parent.find_all(current.name, recursive=False)]
            index = siblings.index(current) + 1 if current in siblings else 1
            parts.append(f"{current.name}[{index}]")
            current = parent
        parts.reverse()
        return " > ".join(parts[:8])
