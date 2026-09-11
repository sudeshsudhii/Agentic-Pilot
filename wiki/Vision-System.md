# Vision System & Visual Coordinate Grounding

While standard web automation frameworks rely exclusively on the DOM tree, modern web applications frequently embed dynamic canvas elements, SVG charts, obfuscated class names, or deeply nested shadow DOM trees. The **Vision System** in Agentic Pilot provides visual fallback capabilities using local Vision-Language Models (VLMs) hosted in Ollama.

---

## Multimodal Perception Pipeline

The vision system operates as a hybrid grounding engine, activating when DOM extraction is insufficient or when the recovery engine escalates to `vision_fallback`.

```mermaid
flowchart TD
    PAGE["Playwright Browser Page"] --> CAPTURE["Capture Viewport Screenshot<br/>(PNG Buffer)"]
    CAPTURE --> HASH["Compute SHA-256 Key<br/>(screenshot_bytes + goal + target)"]

    HASH --> CACHE_CHECK{"Cache Hit?<br/>(Screen & Goal Unchanged)"}
    CACHE_CHECK -->|Yes| HIT["Return Cached VisionAction<br/>(Bypass VLM inference)"]
    CACHE_CHECK -->|No| PROBE{"Is Vision Model Installed?<br/>(Ollama /api/tags probe)"}

    PROBE -->|No Vision Model| ERR["Raise VisionUnavailableError<br/>(Trigger Recovery Escalation)"]
    PROBE -->|Model Found| INFER["Dispatch Multimodal Prompt<br/>(OllamaGateway: Image + System Prompt)"]

    INFER --> PARSE["Parse VisionAction JSON<br/>(action_type, text, x_percent, y_percent)"]
    PARSE --> STORE["Store in Memory Cache<br/>(Max 30 items)"]
    STORE --> TRANSLATE["Coordinate Grounding<br/>(Normalize 0.0-1.0 to Viewport Pixels)"]
    HIT --> TRANSLATE

    TRANSLATE --> DISPATCH["Playwright Mouse Dispatch<br/>page.mouse.click(px, py)"]

    classDef procStyle fill:#0f172a,stroke:#38bdf8,stroke-width:1.5px,color:#f8fafc;
    classDef checkStyle fill:#1e1b4b,stroke:#a855f7,stroke-width:1.5px,color:#f8fafc;
    class CAPTURE,HASH,INFER,PARSE,STORE,TRANSLATE,DISPATCH procStyle;
    class CACHE_CHECK,PROBE checkStyle;
```

---

## Visual Coordinate Grounding

Rather than requiring the local VLM to output absolute pixel coordinates (which vary by display scaling, DPI, and window size), Agentic Pilot standardizes on **Normalized Relative Coordinates**:

* `x_percent`: Float value between `0.0` (left edge) and `1.0` (right edge).
* `y_percent`: Float value between `0.0` (top edge) and `1.0` (bottom edge).
* Exact Center: `x = 0.5, y = 0.5`.

### Translation to Playwright Viewport Pixels

When a `VisionAction` is returned, the executor translates relative coordinates into physical pixels using the current Playwright page viewport dimensions:

$$\text{Pixel}_X = \lfloor x_{\text{percent}} \times \text{Viewport Width} \rfloor$$
$$\text{Pixel}_Y = \lfloor y_{\text{percent}} \times \text{Viewport Height} \rfloor$$

```mermaid
sequenceDiagram
    autonumber
    participant Node as plan_action_node / recovery_node
    participant Fallback as VisionFallback (backend/vision/fallback.py)
    participant Ollama as Ollama Daemon (:11434)
    participant Browser as Playwright Page

    Node->>Browser: page.screenshot(type="png")
    Browser-->>Node: Raw PNG Bytes
    Node->>Fallback: plan_action(screenshot_bytes, goal, target)
    
    Fallback->>Ollama: POST /api/generate<br/>Prompt + Base64 Image<br/>(Model: moondream / qwen3-vl:2b)
    Ollama-->>Fallback: JSON: { action_type: "click", x_percent: 0.45, y_percent: 0.22 }

    Fallback-->>Node: VisionAction Object
    Node->>Browser: Translate (0.45 * 1280 = 576px, 0.22 * 800 = 176px)
    Node->>Browser: page.mouse.click(576, 176)
    Browser-->>Node: Click Dispatched
```

---

## Screenshot Hashing & Inference Caching

Local VLM inference on consumer hardware can take between 800ms and 3,500ms depending on parameter size. To avoid redundant compute cycles during multi-step tasks where the screen has not changed:

1. **Hash Generation**: `VisionFallback` computes a SHA-256 hash combining:
   * Raw image byte buffer.
   * Active step goal string.
   * Target element description string.
2. **Cache Eviction**: A lightweight LRU cache (default: 30 entries) retains recent inferences.
3. **Short-Circuit**: If the agent re-evaluates the page without visual changes, the previous `VisionAction` is reused instantly, reducing latency to < 1ms.

---

## Supported Local Vision Models

The framework prioritizes compact, high-efficiency vision models suited for local execution:

1. **`moondream:latest` (~1.6B)**:
   * Recommended for entry-level GPUs (4 GB to 8 GB VRAM).
   * Fast coordinate localization, low memory overhead.
2. **`qwen3-vl:2b` (2B)**:
   * Balanced vision model with strong OCR and UI element detection.
3. **`qwen2.5-vl:7b` (7B)**:
   * High-accuracy grounding for complex dashboards and low-contrast interfaces.

If visual analysis is invoked but no vision-capable model is discovered in Ollama, the system raises a `VisionUnavailableError` and safely redirects the execution flow to the `RecoveryEngine` without crashing.

---

*Related Pages:*
* [[Local LLM & Model Routing|Local-LLM-and-Model-Routing]]
* [[Browser Automation|Browser-Automation]]
* [[CAPTCHA & Failure Recovery|CAPTCHA-and-Failure-Recovery]]
