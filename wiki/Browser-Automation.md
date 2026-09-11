# Browser Automation & DOM Extraction

The browser automation tier in **Agentic Pilot** is powered by an asynchronous **Playwright** runtime. It translates high-level task intents into concrete web interactions using an intelligent DOM extraction pipeline, stealth anti-detection configurations, and a resilient multi-tier locator resolution hierarchy.

---

## The Resilient Locator Resolution Hierarchy

Brittle selectors are the leading cause of automation failure. Agentic Pilot resolves target elements by descending through a prioritized locator ladder before escalating to visual coordinate grounding:

```mermaid
flowchart TD
    TARGET["Target Element Selected by LLM<br/>(InteractiveElement)"] --> L1

    subgraph LocatorLadder ["Selector Resolution Hierarchy"]
        L1{"1. Unique HTML ID?<br/>(#submit-btn)"}
        L1 -->|Found| EXEC_ID["Execute via ID Locator"]
        L1 -->|No ID / Stale| L2{"2. Accessible Role & Name?<br/>(role='button', name='Sign In')"}

        L2 -->|Found| EXEC_ROLE["Execute via Playwright get_by_role()"]
        L2 -->|Ambiguous / Missing| L3{"3. Visible Element Text?<br/>(get_by_text('Continue'))"}

        L3 -->|Found| EXEC_TEXT["Execute via Exact/Fuzzy Text"]
        L3 -->|Not Found| L4{"4. Robust CSS Selector?<br/>(form > button.primary)"}

        L4 -->|Found| EXEC_CSS["Execute via CSS Selector"]
        L4 -->|Not Found| L5{"5. Structural XPath?<br/>(//button[contains(@class, 'cta')])"}

        L5 -->|Found| EXEC_XPATH["Execute via XPath"]
        L5 -->|Exhausted| L6["6. Vision Coordinate Fallback<br/>(VLM Normalization: px, py)"]
    end

    EXEC_ID --> DISPATCH["Dispatch Event via Playwright CDP"]
    EXEC_ROLE --> DISPATCH
    EXEC_TEXT --> DISPATCH
    EXEC_CSS --> DISPATCH
    EXEC_XPATH --> DISPATCH
    L6 --> DISPATCH

    classDef checkStyle fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#f8fafc;
    classDef execStyle fill:#1e1b4b,stroke:#a855f7,stroke-width:1.5px,color:#f8fafc;
    class L1,L2,L3,L4,L5 checkStyle;
    class EXEC_ID,EXEC_ROLE,EXEC_TEXT,EXEC_CSS,EXEC_XPATH,L6 execStyle;
```

---

## Interactive DOM Extraction Pipeline

Sending full raw HTML documents to local LLMs overflows context windows and degrades reasoning quality. The `DOMExtractor` (`backend/browser/dom.py`) parses the page into an optimized accessibility tree:

```mermaid
flowchart LR
    RAW["Raw Page DOM<br/>(~500 KB HTML)"] --> PRUNE["Tree Pruning<br/>(Remove script, style, SVG path, invisible nodes)"]
    PRUNE --> FILTER["Interactive Element Filtering<br/>(a, button, input, select, textarea, [role=button])"]
    FILTER --> ATTR["Attribute Extraction<br/>(id, name, placeholder, aria-label, href)"]
    ATTR --> INDEX["Sequential Index Assignment<br/>([0], [1], [2]...)"]
    INDEX --> MANIFEST["ActionManifest<br/>(~5 KB Structured JSON)"]
```

### Element Filtering Rules
1. **Visibility Check**: Elements with `display: none`, `visibility: hidden`, or zero bounding boxes (`width == 0` or `height == 0`) are discarded.
2. **Interactive Tags**: Prioritizes `<a>`, `<button>`, `<input>`, `<select>`, `<textarea>`, and elements with `tabindex` or explicit ARIA roles.
3. **Sequential IDs**: Elements receive clean integer identifiers (`[ID 0]`, `[ID 1]`, etc.) allowing local LLMs to choose actions using concise integers rather than complex CSS strings.

---

## Core Browser Actions

The `ActionExecutor` (`backend/browser/actions.py`) handles atomic browser commands with built-in execution timing and state tracking:

| Action | Function Signature | Description & Verification Hooks |
| :--- | :--- | :--- |
| `navigate` | `navigate(page, url)` | Navigates to target URL with `domcontentloaded` wait. Checks for `chrome-error://` pages. |
| `click` | `click(page, element)` | Dispatches mouse click on element. Verifies subsequent DOM mutation. |
| `type_text` | `type_text(page, element, text)` | Types text character-by-character into text inputs, search bars, or textareas. |
| `select_option`| `select_option(page, element, value)` | Selects dropdown options in native HTML `<select>` elements. |
| `scroll` | `scroll(page, direction, amount)` | Scrolls viewport vertically or horizontally to bring elements into view. |

---

## Browser Session Management & Stealth Evasion

The browser pool (`backend/browser/pool.py`) launches Chromium instances configured to prevent automated bot fingerprinting:

* **User-Agent Spoofing**: Configures modern, standard desktop user-agents (e.g., Chrome on Windows/macOS).
* **WebDriver Flag Elimination**: Disables `navigator.webdriver` flags and automation banners.
* **Viewport Normalization**: Enforces standard desktop viewports (1280x800) with proper device scale factors.
* **Headless / Headful Toggling**: Supports both headless operation for background automation and headful display for developer debugging.

---

*Related Pages:*
* [[Vision System|Vision-System]]
* [[Evidence & Verification|Evidence-and-Verification]]
* [[CAPTCHA & Failure Recovery|CAPTCHA-and-Failure-Recovery]]
